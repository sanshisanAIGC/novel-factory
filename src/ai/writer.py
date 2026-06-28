"""
AI 作者 Agent
负责按指定风格批量写作小说章节
"""
import json
import re
from pathlib import Path
from .client import DeepSeekClient
from .prompts import (
    WRITER_SYSTEM_PROMPT,
    WRITER_USER_PROMPT,
    CHAPTER_PLAN_PROMPT,
)


class AIWriter:
    """AI 作者 — 批量写作小说章节"""

    def __init__(self, client: DeepSeekClient, state_manager, context_manager, style_profile: dict):
        self.client = client
        self.state = state_manager
        self.context = context_manager
        self.style = style_profile

    def write_batch(
        self,
        num_chapters: int = 10,
        min_words: int = 2000,
        max_words: int = 3000,
    ) -> list[dict]:
        """
        批量写作章节

        Args:
            num_chapters: 写作章节数
            min_words: 每章最少字数
            max_words: 每章最多字数

        Returns:
            [{chapter_number, title, content, word_count}, ...]
        """
        novel = self.state.get_novel_info()
        current_ch = novel["current_chapter"]

        # Step 1: 生成章节大纲
        print(f"\n{'='*60}")
        print(f"[Writer] 生成第 {current_ch + 1} 到 {current_ch + num_chapters} 章的大纲...")
        plan = self._generate_chapter_plan(num_chapters)
        print(f"[Writer] 大纲生成完成，弧名: {plan.get('arc_name', '未命名')}")

        # Step 2: 逐章写作
        chapters = []
        for i, ch_plan in enumerate(plan.get("chapters", [])):
            ch_num = current_ch + i + 1
            print(f"\n[Writer] 写作第 {ch_num} 章 ({i+1}/{num_chapters})...")

            chapter = self._write_single_chapter(
                chapter_number=ch_num,
                chapter_plan=ch_plan,
                previous_chapter=chapters[-1] if chapters else None,
                min_words=min_words,
                max_words=max_words,
            )

            chapters.append(chapter)

            # 保存单章到文件
            self._save_chapter(chapter)

            # 更新内存状态
            self._update_state_after_chapter(chapter, ch_plan)

            word_count = chapter["word_count"]
            print(f"[Writer] 第 {ch_num} 章完成: {word_count} 字")

        # Step 3: 更新 state.json
        self.state.set("novel.current_chapter", current_ch + num_chapters)
        self.state.save()

        print(f"\n[Writer] 批次完成！共 {len(chapters)} 章")
        total_words = sum(c["word_count"] for c in chapters)
        print(f"[Writer] 总字数: {total_words}")

        return chapters

    def _generate_chapter_plan(self, num_chapters: int) -> dict:
        """生成章节大纲"""
        novel = self.state.get_novel_info()
        current_ch = novel["current_chapter"]

        prompt = CHAPTER_PLAN_PROMPT.format(
            num_chapters=num_chapters,
            novel_title=novel["title"],
            novel_genre=novel["genre"],
            current_chapter=current_ch,
            total_chapters=novel["total_chapters_planned"],
            character_table=self.context.get_character_table(),
            foreshadowing_table=self.context.get_foreshadowing_table(),
            recent_summaries=self.context.get_recent_summaries(),
            start_chapter=current_ch + 1,
            end_chapter=current_ch + num_chapters,
        )

        resp = self.client.chat_with_retry(
            system_prompt="你是一位专业的小说策划编辑。请严格以 JSON 格式输出结果。",
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=4096,
        )

        # 解析 JSON
        return self._parse_json_response(resp)

    def _write_single_chapter(
        self,
        chapter_number: int,
        chapter_plan: dict,
        previous_chapter: dict | None,
        min_words: int,
        max_words: int,
    ) -> dict:
        """写作单章"""
        novel = self.state.get_novel_info()

        # 构建 System Prompt
        system_prompt = WRITER_SYSTEM_PROMPT.format(
            min_words=min_words,
            max_words=max_words,
            style_profile=json.dumps(self.style, ensure_ascii=False, indent=2),
            world_rules=json.dumps(self.state.get_world_rules(), ensure_ascii=False, indent=2),
        )

        # 前文结尾
        prev_ending = ""
        if previous_chapter:
            content = previous_chapter["content"]
            # 取最后 300 字作为衔接
            prev_ending = content[-300:] if len(content) > 300 else content
        else:
            # 从已有章节取结尾
            prev_ending = self.context.get_last_chapter_ending()

        # 伏笔指示
        foreshadowing_instruction = ""
        resolve_list = chapter_plan.get("resolve_foreshadowing", [])
        new_list = chapter_plan.get("new_foreshadowing", [])
        if resolve_list:
            foreshadowing_instruction += f"需要回收的伏笔：{', '.join(resolve_list)}。"
        if new_list:
            foreshadowing_instruction += f"可以埋设新伏笔：{', '.join(new_list)}。"
        if not foreshadowing_instruction:
            foreshadowing_instruction = "根据剧情需要决定是否埋设新伏笔，如有合适的旧伏笔可以回收。"

        # 构建 User Prompt
        user_prompt = WRITER_USER_PROMPT.format(
            novel_title=novel["title"],
            novel_genre=novel["genre"],
            current_volume=novel["current_volume"],
            current_chapter=novel["current_chapter"],
            target_chapter=chapter_number,
            total_chapters=novel["total_chapters_planned"],
            character_table=self.context.get_character_table(),
            recent_summaries=self.context.get_recent_summaries(),
            foreshadowing_table=self.context.get_foreshadowing_table(),
            chapter_plan=json.dumps(chapter_plan, ensure_ascii=False, indent=2),
            previous_chapter_ending=prev_ending,
            min_words=min_words,
            max_words=max_words,
            foreshadowing_instruction=foreshadowing_instruction,
        )

        # 调用 API
        content = self.client.chat_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.85,
            max_tokens=max_words * 3,  # 中文约 1.5 字符/token，留足余量
        )

        # 清理输出
        content = self._clean_chapter_content(content)

        # 估计字数
        word_count = len(content.replace("\n", "").replace(" ", ""))

        return {
            "chapter_number": chapter_number,
            "title": chapter_plan.get("core_event", f"第{chapter_number}章")[:30],
            "content": content,
            "word_count": word_count,
            "plan": chapter_plan,
        }

    def _clean_chapter_content(self, content: str) -> str:
        """清理 AI 生成的章节内容"""
        # 移除可能的 Markdown 代码块标记
        content = re.sub(r'^```[a-z]*\s*\n', '', content)
        content = re.sub(r'\n```\s*$', '', content)

        # 移除 AI 可能添加的章节标题
        content = re.sub(r'^第[零一二三四五六七八九十百千\d]+章[^\n]*\n*', '', content)

        # 移除开头和结尾的空白
        content = content.strip()

        return content

    def _save_chapter(self, chapter: dict):
        """保存章节到文件"""
        ch_num = chapter["chapter_number"]
        filepath = self.state.chapters_dir / f"chapter_{ch_num:04d}.txt"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(chapter["content"], encoding="utf-8")
        print(f"  已保存: {filepath.name}")

    def _update_state_after_chapter(self, chapter: dict, chapter_plan: dict):
        """写作后更新状态（轻量更新，详细分析由 Editor 完成）"""
        ch_num = chapter["chapter_number"]
        summary = chapter["content"][:200] + "..." if len(chapter["content"]) > 200 else chapter["content"]

        event = chapter_plan.get("core_event", "剧情推进")
        self.state.add_chapter_summary(ch_num, summary, [event])

    @staticmethod
    def _parse_json_response(resp: str) -> dict:
        """解析 AI 返回的 JSON"""
        # 尝试提取 ```json ... ``` 代码块
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', resp, re.DOTALL)
        if m:
            resp = m.group(1)
        try:
            return json.loads(resp)
        except json.JSONDecodeError:
            # 尝试查找第一个 { 和最后一个 }
            start = resp.find('{')
            end = resp.rfind('}')
            if start >= 0 and end > start:
                return json.loads(resp[start:end + 1])
            raise RuntimeError(f"无法解析 AI 返回的 JSON: {resp[:500]}")
