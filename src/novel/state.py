"""
小说状态管理
JSON 持久化：人物、世界观、伏笔、章节摘要等
"""
import json
import time
from pathlib import Path
from datetime import datetime


class NovelState:
    """小说全局状态管理器"""

    def __init__(self, state_file: Path, chapters_dir: Path):
        self.state_file = state_file
        self.chapters_dir = chapters_dir
        self.data = self._load()

    def _load(self) -> dict:
        """加载状态文件，不存在则创建默认状态"""
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return self._default_state()

    def _default_state(self) -> dict:
        """创建默认的小说状态结构"""
        return {
            "novel": {
                "title": "",
                "genre": "",
                "total_chapters_planned": 500,
                "current_chapter": 0,
                "current_volume": 1,
                "chapters_per_batch": 10,
            },
            "characters": [],
            "world": {
                "setting": "",
                "key_rules": [],
                "locations": [],
            },
            "foreshadowing": [],
            "chapter_summaries": [],
            "batches": [],
            "style_profile": {},
            "meta": {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "1.0",
            },
        }

    def save(self):
        """保存状态到文件"""
        self.data["meta"]["updated_at"] = datetime.now().isoformat()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, path: str, default=None):
        """通过点分隔路径获取值，如 'novel.current_chapter'"""
        keys = path.split(".")
        value = self.data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value

    def set(self, path: str, value):
        """通过点分隔路径设置值"""
        keys = path.split(".")
        target = self.data
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    # ━━━━ 小说基本信息 ━━━━

    def get_novel_info(self) -> dict:
        """获取小说基本信息"""
        return self.data["novel"]

    def init_novel(self, title: str, genre: str = "", total_chapters: int = 500):
        """初始化小说基本信息"""
        self.data["novel"].update({
            "title": title,
            "genre": genre,
            "total_chapters_planned": total_chapters,
            "current_chapter": 0,
        })
        self.save()

    def set_style_profile(self, profile: dict):
        """设置风格画像"""
        self.data["style_profile"] = profile
        self.save()

    def get_style_profile(self) -> dict:
        """获取风格画像"""
        return self.data.get("style_profile", {})

    # ━━━━ 人物管理 ━━━━

    def add_character(self, name: str, role: str = "supporting", traits: list = None,
                      description: str = "", relationships: dict = None):
        """添加人物"""
        char = {
            "id": f"char_{len(self.data['characters']) + 1:03d}",
            "name": name,
            "role": role,  # protagonist, antagonist, supporting, minor
            "traits": traits or [],
            "description": description,
            "current_status": "",
            "last_appeared_chapter": 0,
            "unresolved_conflicts": [],
            "relationships": relationships or {},
        }
        self.data["characters"].append(char)
        self.save()
        return char["id"]

    def get_character(self, name: str) -> dict | None:
        """按名称查找人物"""
        for c in self.data["characters"]:
            if c["name"] == name:
                return c
        return None

    def update_character_status(self, char_id: str, status: str, chapter: int):
        """更新人物状态"""
        for c in self.data["characters"]:
            if c["id"] == char_id:
                c["current_status"] = status
                c["last_appeared_chapter"] = chapter
                self.save()
                return

    def get_characters_table(self) -> list[dict]:
        """获取人物简表（用于 prompt 上下文）"""
        return [
            {
                "id": c["id"],
                "name": c["name"],
                "role": c["role"],
                "traits": c["traits"],
                "current_status": c["current_status"],
                "last_appeared": c["last_appeared_chapter"],
                "relationships": c["relationships"],
            }
            for c in self.data["characters"]
        ]

    # ━━━━ 世界观 ━━━━

    def set_world(self, setting: str, rules: list = None, locations: list = None):
        """设置世界观"""
        self.data["world"].update({
            "setting": setting,
            "key_rules": rules or [],
            "locations": locations or [],
        })
        self.save()

    def get_world_rules(self) -> dict:
        """获取世界观设定"""
        return self.data["world"]

    # ━━━━ 伏笔管理 ━━━━

    def add_foreshadowing(self, content: str, planted_chapter: int,
                          planned_resolution: int = None):
        """添加新伏笔"""
        fs = {
            "id": f"fs_{len(self.data['foreshadowing']) + 1:03d}",
            "content": content,
            "planted_chapter": planted_chapter,
            "planned_resolution_chapter": planned_resolution,
            "status": "active",
            "resolved_chapter": None,
            "resolved_content": None,
        }
        self.data["foreshadowing"].append(fs)
        self.save()
        return fs["id"]

    def resolve_foreshadowing(self, content: str, resolved_chapter: int):
        """回收伏笔 — 通过内容匹配"""
        for fs in self.data["foreshadowing"]:
            if fs["status"] == "active" and content in fs.get("content", ""):
                fs["status"] = "resolved"
                fs["resolved_chapter"] = resolved_chapter
                fs["resolved_content"] = content
                self.save()
                return True
        # 如果没找到精确匹配，标记最近的活跃伏笔
        for fs in reversed(self.data["foreshadowing"]):
            if fs["status"] == "active":
                fs["status"] = "resolved"
                fs["resolved_chapter"] = resolved_chapter
                fs["resolved_content"] = content
                self.save()
                return True
        return False

    def get_active_foreshadowing(self) -> list[dict]:
        """获取所有未回收的伏笔"""
        return [fs for fs in self.data["foreshadowing"] if fs["status"] == "active"]

    def get_all_foreshadowing(self) -> list[dict]:
        """获取所有伏笔"""
        return self.data["foreshadowing"]

    # ━━━━ 章节摘要 ━━━━

    def add_chapter_summary(self, chapter_num: int, summary: str, key_events: list = None):
        """添加/更新章节摘要"""
        for s in self.data["chapter_summaries"]:
            if s["chapter"] == chapter_num:
                s["summary"] = summary
                s["key_events"] = key_events or []
                self.save()
                return

        self.data["chapter_summaries"].append({
            "chapter": chapter_num,
            "summary": summary,
            "key_events": key_events or [],
        })
        self.save()

    def get_recent_summaries(self, count: int = 10) -> list[dict]:
        """获取最近 N 章的摘要"""
        sorted_summaries = sorted(
            self.data["chapter_summaries"],
            key=lambda s: s["chapter"],
            reverse=True,
        )
        return sorted_summaries[:count][::-1]  # 按章节顺序返回

    def get_last_chapter_ending(self) -> str:
        """获取最后一章的结尾（用于上下文衔接）"""
        current = self.data["novel"]["current_chapter"]
        if current == 0:
            return "（这是小说的开篇）"

        # 尝试从文件读取
        filepath = self.chapters_dir / f"chapter_{current:04d}.txt"
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            return content[-300:] if len(content) > 300 else content

        # 回退到摘要
        summaries = self.get_recent_summaries(1)
        if summaries:
            return f"上一章摘要：{summaries[0]['summary']}"

        return "（无前文）"

    # ━━━━ 批次管理 ━━━━

    def add_batch(self, chapters: list[int], score: float, status: str):
        """记录一个批次"""
        batch = {
            "batch_id": len(self.data["batches"]) + 1,
            "chapters": chapters,
            "editor_score": score,
            "status": status,  # draft, approved, published
            "created_at": datetime.now().isoformat(),
        }
        self.data["batches"].append(batch)
        self.save()
        return batch["batch_id"]

    def get_approved_chapters(self) -> list[int]:
        """获取所有已审核通过的章节号"""
        approved = []
        for batch in self.data["batches"]:
            if batch["status"] == "approved":
                approved.extend(batch["chapters"])
        return sorted(approved)

    # ━━━━ 导入已有小说 ━━━━

    def import_from_text(self, title: str, content: str, genre: str = "",
                         wiki_token: str = "", space_id: str = "", node_token: str = "",
                         document_id: str = ""):
        """
        从纯文本导入已有小说
        尝试按章节标题自动分割
        """
        import re

        # 设置标题
        self.data["novel"]["title"] = title
        self.data["novel"]["genre"] = genre

        # 保存飞书 Wiki 信息（用于后续同步）
        if wiki_token:
            self.data["novel"]["fs_wiki_token"] = wiki_token
        if space_id:
            self.data["novel"]["fs_space_id"] = space_id
        if node_token:
            self.data["novel"]["fs_node_token"] = node_token
        if document_id:
            self.data["novel"]["fs_document_id"] = document_id

        # 匹配 "第X章：标题" 格式（中文数字或阿拉伯数字）
        pattern = r'(第[零一二三四五六七八九十百千\d]+章[：:][^\n]*)'
        parts = re.split(pattern, content)

        if len(parts) <= 1:
            # 没有找到章节标题，整篇作为第一章
            self.data["novel"]["current_chapter"] = 1
            self.data["chapter_summaries"].append({
                "chapter": 1,
                "summary": content[:200],
                "key_events": [],
            })
            # 保存完整内容
            filepath = self.chapters_dir / "chapter_0001.txt"
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            print(f"[State] 导入 1 章（未检测到章节标题），共 {len(content)} 字符")
        else:
            # 清理旧的章节文件
            for old_file in self.chapters_dir.glob("chapter_*.txt"):
                old_file.unlink()

            # 清除旧的摘要
            self.data["chapter_summaries"] = []

            # parts[0] 是第一个标题前的内容（简介/封面描述，跳过）
            # parts[1], parts[2], ... 交替出现：标题, 内容
            chapter_num = 0
            for i in range(1, len(parts), 2):
                title_line = parts[i].strip()
                ch_content = parts[i + 1].strip() if i + 1 < len(parts) else ""

                # 跳过内容太短的（可能是误匹配）
                if len(ch_content) < 50:
                    continue

                chapter_num += 1

                # 保存章节
                filepath = self.chapters_dir / f"chapter_{chapter_num:04d}.txt"
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(ch_content, encoding="utf-8")

                # 添加摘要（取前 200 字）
                summary = ch_content[:200].replace("\n", " ").replace("\r", " ")
                self.data["chapter_summaries"].append({
                    "chapter": chapter_num,
                    "summary": summary,
                    "key_events": [],
                })

            self.data["novel"]["current_chapter"] = chapter_num
            print(f"[State] 导入 {chapter_num} 章（跳过 {len(parts)//2 - chapter_num} 个空章节），总计约 {len(content)} 字符")

        self.save()
        return self.data["novel"]["current_chapter"]

    def get_stats(self) -> dict:
        """获取小说统计信息"""
        current = self.data["novel"]["current_chapter"]
        total_words = 0
        for ch_num in range(1, current + 1):
            filepath = self.chapters_dir / f"chapter_{ch_num:04d}.txt"
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                total_words += len(content.replace("\n", "").replace(" ", ""))

        return {
            "total_chapters": current,
            "total_words": total_words,
            "avg_words_per_chapter": total_words // current if current > 0 else 0,
            "characters_count": len(self.data["characters"]),
            "active_foreshadowing": len(self.get_active_foreshadowing()),
            "resolved_foreshadowing": len([fs for fs in self.data["foreshadowing"] if fs["status"] == "resolved"]),
            "batches_count": len(self.data["batches"]),
            "approved_chapters": len(self.get_approved_chapters()),
        }
