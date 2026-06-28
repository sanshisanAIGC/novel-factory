"""
流程编排模块
协调 Writer → Editor → Sync 的完整工作流
"""
import time
from pathlib import Path
from src.ai.client import DeepSeekClient
from src.ai.writer import AIWriter
from src.ai.editor import AIEditor
from src.novel.state import NovelState
from src.novel.style import StyleExtractor
from src.novel.context import ContextManager
from src.feishu.auth import FeishuAuth
from src.feishu.wiki_reader import WikiReader
from src.feishu.wiki_writer import WikiWriter


class NovelPipeline:
    """小说创作流水线"""

    def __init__(
        self,
        deepseek_api_key: str,
        deepseek_base_url: str = "https://api.deepseek.com",
        deepseek_model: str = "deepseek-v4-pro",
        feishu_app_id: str = "",
        feishu_app_secret: str = "",
        data_dir: Path = None,
    ):
        # 初始化路径
        if data_dir is None:
            data_dir = Path("data")
        self.data_dir = Path(data_dir)
        self.chapters_dir = self.data_dir / "chapters"
        self.state_file = self.data_dir / "state.json"
        self.style_file = self.data_dir / "style_profile.json"

        # 初始化组件
        self.ai_client = DeepSeekClient(
            api_key=deepseek_api_key,
            base_url=deepseek_base_url,
            model=deepseek_model,
        )
        self.state = NovelState(self.state_file, self.chapters_dir)
        self.context = ContextManager(self.state)
        self.editor = AIEditor(self.ai_client, self.state, self.context)

        # 飞书
        self.feishu_auth = None
        if feishu_app_id and feishu_app_secret:
            self.feishu_auth = FeishuAuth(feishu_app_id, feishu_app_secret)

        # Writer 和 StyleExtractor 需要 style_profile
        style_profile = self.state.get_style_profile()
        self.style_extractor = StyleExtractor(self.ai_client)
        self.writer = AIWriter(self.ai_client, self.state, self.context, style_profile)

    # ━━━━ 初始化 ━━━━

    def init_from_wiki(self, wiki_token: str) -> dict:
        """从飞书 Wiki 初始化项目"""
        if not self.feishu_auth:
            raise RuntimeError("飞书未配置，无法读取 Wiki")

        print("[Pipeline] 从飞书 Wiki 初始化...")

        reader = WikiReader(self.feishu_auth)
        novel_data = reader.read_novel_from_wiki(wiki_token)

        # 保存原始内容
        reader.save_to_file(novel_data["content"], self.data_dir / "original_novel.txt")

        # 导入章节（同时保存 Wiki 信息用于后续同步）
        chapter_count = self.state.import_from_text(
            title=novel_data["title"],
            content=novel_data["content"],
            wiki_token=wiki_token,
            space_id=novel_data.get("space_id", ""),
            node_token=novel_data.get("node_token", ""),
            document_id=novel_data.get("document_id", ""),
        )

        # 提取风格
        print("\n[Pipeline] 提取写作风格...")
        style_profile = self.style_extractor.extract_from_chapters(self.chapters_dir)
        self.style_extractor.save_profile(style_profile, self.style_file)
        self.state.set_style_profile(style_profile)
        self.writer.style = style_profile  # 更新 writer 的风格引用

        print(f"\n[Pipeline] 初始化完成！")
        print(f"  书名: {novel_data['title']}")
        print(f"  章节: {chapter_count} 章")
        stats = self.state.get_stats()
        print(f"  总字数: {stats['total_words']}")

        return novel_data

    def init_from_file(self, title: str, filepath: Path, genre: str = ""):
        """从本地文件初始化（用于测试）"""
        content = filepath.read_text(encoding="utf-8")

        chapter_count = self.state.import_from_text(title, content, genre)

        print("[Pipeline] 提取写作风格...")
        style_profile = self.style_extractor.extract_from_chapters(self.chapters_dir)
        self.style_extractor.save_profile(style_profile, self.style_file)
        self.state.set_style_profile(style_profile)
        self.writer.style = style_profile

        print(f"[Pipeline] 初始化完成！{chapter_count} 章")

    # ━━━━ 写作流程 ━━━━

    def run_write_batch(
        self,
        num_chapters: int = 10,
        min_words: int = 2000,
        max_words: int = 3000,
    ) -> list[dict]:
        """AI 作者写一批章节"""
        print(f"\n{'='*60}")
        print(f"[Pipeline] 开始写作批次: {num_chapters} 章")
        print(f"{'='*60}")

        chapters = self.writer.write_batch(
            num_chapters=num_chapters,
            min_words=min_words,
            max_words=max_words,
        )

        # 记录批次
        chapter_nums = [c["chapter_number"] for c in chapters]
        self.state.add_batch(chapter_nums, 0, "draft")

        return chapters

    # ━━━━ 审核流程 ━━━━

    def run_review_batch(self, chapters: list[dict]) -> dict:
        """AI 编辑审核一批章节"""
        result = self.editor.review_batch(chapters)

        # 更新状态
        chapter_nums = [c["chapter_number"] for c in chapters]
        batch_id = self.state.add_batch(
            chapter_nums,
            result["batch_score"],
            "approved" if result["batch_verdict"] != "FAIL" else "draft",
        )

        result["batch_id"] = batch_id

        # 从审核中提取状态更新
        for review in result.get("chapter_reviews", []):
            self.editor.update_state_from_review(review)

        self.state.save()
        return result

    # ━━━━ 修改流程 ━━━━

    def run_revise_chapter(self, chapter_number: int, review: dict) -> dict:
        """根据编辑反馈修改单章"""
        feedback = self.editor.get_revision_feedback(chapter_number, review)
        print(f"[Pipeline] 修改第 {chapter_number} 章...")

        # 用反馈作为额外的写作指导
        chapter_plan = {
            "core_event": f"基于编辑反馈修改第{chapter_number}章",
            "characters_involved": [],
            "plot_lines_advanced": [],
            "new_foreshadowing": [],
            "resolve_foreshadowing": [],
            "emotional_tone": "",
            "revision_feedback": feedback,
        }

        # 使用 writer 重写
        chapter = self.writer._write_single_chapter(
            chapter_number=chapter_number,
            chapter_plan=chapter_plan,
            previous_chapter=None,
            min_words=2000,
            max_words=3000,
        )

        self.writer._save_chapter(chapter)
        return chapter

    # ━━━━ 飞书同步 ━━━━

    def run_sync_to_feishu(self, chapter_numbers: list[int]) -> list[dict]:
        """将审核通过的章节同步到飞书 Wiki"""
        if not self.feishu_auth:
            raise RuntimeError("飞书未配置，无法同步")

        print(f"\n[Pipeline] 同步章节到飞书: {chapter_numbers}")

        # 获取 space_id（需要先通过 wiki reader 获取）
        wiki_token = self.state.get("novel.fs_wiki_token", "")
        space_id = ""
        parent_token = ""

        if wiki_token:
            reader = WikiReader(self.feishu_auth)
            node_info = reader.resolve_wiki_token(wiki_token)
            space_id = node_info["space_id"]
            parent_token = node_info["node_token"]

        wiki_doc_id = self.state.get("novel.fs_document_id", "")
        writer = WikiWriter(self.feishu_auth, space_id, parent_token, wiki_doc_id)

        chapters = []
        for ch_num in chapter_numbers:
            filepath = self.chapters_dir / f"chapter_{ch_num:04d}.txt"
            if not filepath.exists():
                print(f"[Pipeline] 第 {ch_num} 章文件不存在，跳过")
                continue

            content = filepath.read_text(encoding="utf-8")
            chapters.append({
                "chapter_num": ch_num,
                "title": f"第{ch_num}章",
                "content": content,
            })

        if not chapters:
            print("[Pipeline] 没有需要同步的章节")
            return []

        results = writer.batch_sync_chapters(chapters, f"Batch_{chapter_numbers[0]}_{chapter_numbers[-1]}")

        # 更新批次状态
        for batch in self.state.data["batches"]:
            if set(batch["chapters"]) == set(chapter_numbers):
                batch["status"] = "synced"
                break
        self.state.save()

        return results

    # ━━━━ 完整流程 ━━━━

    def run_full_cycle(
        self,
        num_chapters: int = 10,
        min_words: int = 2000,
        max_words: int = 3000,
        auto_sync: bool = True,
        max_revise_rounds: int = 3,
    ) -> dict:
        """
        运行完整的写作→审核→修改→同步流程

        Args:
            num_chapters: 每批写作章数
            min_words: 每章最少字数
            max_words: 每章最多字数
            auto_sync: 是否自动同步到飞书
            max_revise_rounds: 最大修改轮数（FAIL 时）

        Returns:
            流程结果摘要
        """
        start_time = time.time()

        # Step 1: 写作
        chapters = self.run_write_batch(num_chapters, min_words, max_words)

        # Step 2: 审核
        review = self.run_review_batch(chapters)

        # Step 3: 修改循环（如果 FAIL）
        revise_rounds = 0
        while review["batch_verdict"] == "FAIL" and revise_rounds < max_revise_rounds:
            revise_rounds += 1
            print(f"\n[Pipeline] 第 {revise_rounds} 轮修改...")

            # 只修改 FAIL 的章节
            for ch_review in review["chapter_reviews"]:
                if ch_review.get("verdict") == "FAIL":
                    ch_num = ch_review["chapter_number"]
                    self.run_revise_chapter(ch_num, ch_review)

            # 重新审核
            # 重新读取修改后的章节
            revised_chapters = []
            for ch in chapters:
                filepath = self.chapters_dir / f"chapter_{ch['chapter_number']:04d}.txt"
                if filepath.exists():
                    revised_chapters.append({
                        "chapter_number": ch["chapter_number"],
                        "content": filepath.read_text(encoding="utf-8"),
                    })

            review = self.run_review_batch(revised_chapters)

        elapsed = time.time() - start_time

        # Step 4: 同步到飞书
        sync_results = []
        if auto_sync and review["batch_verdict"] != "FAIL":
            chapter_numbers = [c["chapter_number"] for c in chapters]
            sync_results = self.run_sync_to_feishu(chapter_numbers)

        # Step 5: 打印摘要
        print(f"\n{'='*60}")
        print(f"[Pipeline] 完整流程完成！")
        print(f"  总耗时: {elapsed:.0f} 秒")
        print(f"  章节: {chapters[0]['chapter_number']} - {chapters[-1]['chapter_number']}")
        print(f"  审核: {review['batch_verdict']} ({review['batch_score']}/10)")
        print(f"  修改轮数: {revise_rounds}")
        print(f"  同步: {'成功' if sync_results else '跳过'}")
        print(f"{'='*60}")

        return {
            "chapters": chapters,
            "review": review,
            "revise_rounds": revise_rounds,
            "sync_results": sync_results,
            "elapsed_seconds": elapsed,
        }

    # ━━━━ 状态查询 ━━━━

    def print_status(self):
        """打印小说当前状态"""
        stats = self.state.get_stats()
        novel = self.state.get_novel_info()

        print(f"\n{'='*50}")
        print(f"  {novel['title'] or '未命名小说'} - 状态报告")
        print(f"{'='*50}")
        print(f"  总章节:     {stats['total_chapters']}")
        print(f"  总字数:     {stats['total_words']:,}")
        print(f"  平均字数:   {stats['avg_words_per_chapter']}")
        print(f"  人物数量:   {stats['characters_count']}")
        print(f"  活跃伏笔:   {stats['active_foreshadowing']}")
        print(f"  已回收伏笔: {stats['resolved_foreshadowing']}")
        print(f"  批次数量:   {stats['batches_count']}")
        print(f"  已审核章数: {stats['approved_chapters']}")
        print(f"{'='*50}")
