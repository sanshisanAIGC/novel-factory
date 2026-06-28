"""
上下文窗口管理
根据小说长度自动切换上下文策略
"""
import json


class ContextManager:
    """上下文窗口管理器 — 为 AI 提供恰到好处的上下文"""

    def __init__(self, state):
        """
        Args:
            state: NovelState 实例
        """
        self.state = state

    def get_character_table(self) -> str:
        """获取格式化的角色表"""
        chars = self.state.get_characters_table()
        if not chars:
            return "（暂无人物设定）"

        lines = []
        for c in chars:
            role_map = {
                "protagonist": "主角",
                "antagonist": "反派",
                "supporting": "配角",
                "minor": "龙套",
            }
            role = role_map.get(c["role"], c["role"])
            traits = "、".join(c["traits"]) if c["traits"] else "未设定"
            status = c["current_status"] or "未知"
            last = c["last_appeared"] or "未出场"

            line = f"- [{role}] {c['name']}：{traits}。当前状态：{status}。最后出场：第{last}章"

            if c.get("relationships"):
                rel_str = "；".join(f"{k}→{v}" for k, v in c["relationships"].items())
                line += f"。关系：{rel_str}"

            lines.append(line)

        return "\n".join(lines)

    def get_foreshadowing_table(self) -> str:
        """获取格式化的伏笔表"""
        all_fs = self.state.get_all_foreshadowing()
        if not all_fs:
            return "（暂无伏笔记录）"

        active_fs = self.state.get_active_foreshadowing()
        resolved_fs = [fs for fs in all_fs if fs["status"] == "resolved"]

        lines = ["## 已埋伏笔（待回收）"]
        for fs in active_fs:
            planned = f"，计划在第{fs['planned_resolution_chapter']}章回收" if fs.get("planned_resolution_chapter") else ""
            lines.append(f"- {fs['id']}：{fs['content']}（第{fs['planted_chapter']}章埋伏{planned}）")

        if resolved_fs:
            lines.append("\n## 已回收伏笔")
            for fs in resolved_fs[-5:]:  # 只显示最近5个
                lines.append(f"- {fs['id']}：{fs['content']}（第{fs['planted_chapter']}章埋伏 → 第{fs['resolved_chapter']}章回收）")

        return "\n".join(lines)

    def get_recent_summaries(self, count: int = None) -> str:
        """获取最近章节的格式化摘要（根据总章节数自适应）"""
        total_chapters = self.state.get("novel.current_chapter", 0)

        if count is None:
            # 自适应策略
            if total_chapters <= 30:
                count = 20  # 全量（最多 20）
            elif total_chapters <= 100:
                count = 15  # 滑窗
            else:
                count = 10  # 分层摘要

        summaries = self.state.get_recent_summaries(count)

        if not summaries:
            return "（暂无前文章节）"

        lines = [f"最近 {len(summaries)} 章摘要："]
        for s in summaries:
            events = "；".join(s.get("key_events", []))
            lines.append(f"第{s['chapter']}章：{s['summary']}")
            if events:
                lines.append(f"  关键事件：{events}")

        return "\n".join(lines)

    def get_world_rules_text(self) -> str:
        """获取世界观设定的文本描述"""
        world = self.state.get_world_rules()
        setting = world.get("setting", "")
        rules = world.get("key_rules", [])
        locations = world.get("locations", [])

        parts = []
        if setting:
            parts.append(f"世界观背景：{setting}")
        if rules:
            parts.append("核心规则：")
            for r in rules:
                parts.append(f"  - {r}")
        if locations:
            parts.append(f"主要地点：{', '.join(locations)}")

        return "\n".join(parts) if parts else "（暂无世界观设定）"

    def get_last_chapter_ending(self) -> str:
        """获取最后一章的结尾"""
        return self.state.get_last_chapter_ending()

    def build_chapter_context(self, chapter_number: int, chapter_plan: dict) -> str:
        """
        为特定章节构建完整的写作上下文
        这是 Writer 调用前的最终上下文组合
        """
        novel = self.state.get_novel_info()

        parts = [
            f"## 小说信息",
            f"- 书名：{novel['title']}",
            f"- 类型：{novel['genre']}",
            f"- 总规划：{novel['total_chapters_planned']} 章",
            f"- 当前进度：第 {novel['current_volume']} 卷第 {chapter_number} 章",
            "",
            f"## 本章大纲",
            json.dumps(chapter_plan, ensure_ascii=False, indent=2),
            "",
            f"## 人物状态",
            self.get_character_table(),
            "",
            f"## 前文摘要",
            self.get_recent_summaries(),
            "",
            f"## 伏笔跟踪",
            self.get_foreshadowing_table(),
            "",
            f"## 世界观设定",
            self.get_world_rules_text(),
        ]

        return "\n".join(parts)

    def get_context_summary(self) -> str:
        """获取当前上下文的简要摘要（用于日志和调试）"""
        novel = self.state.get_novel_info()
        active_fs = len(self.state.get_active_foreshadowing())
        chars = len(self.state.get_characters_table())

        return (
            f"上下文状态: {novel['current_chapter']} 章, "
            f"{chars} 个人物, "
            f"{active_fs} 个活跃伏笔"
        )
