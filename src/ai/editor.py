"""
AI 编辑 Agent
负责审核章节的剧情一致性、人物关系、伏笔管理等
"""
import json
import re
from .client import DeepSeekClient
from .prompts import EDITOR_SYSTEM_PROMPT, EDITOR_USER_PROMPT


class AIEditor:
    """AI 编辑 — 审核章节质量"""

    def __init__(self, client: DeepSeekClient, state_manager, context_manager):
        self.client = client
        self.state = state_manager
        self.context = context_manager

    def review_chapter(self, chapter_number: int, chapter_content: str) -> dict:
        """
        审核单章

        Returns:
            {
                chapter_number, overall_score, verdict,
                dimensions: {...},
                summary, key_events_extracted,
                new_characters, new_foreshadowing,
                resolved_foreshadowing, character_state_changes
            }
        """
        print(f"[Editor] 审核第 {chapter_number} 章...")

        user_prompt = EDITOR_USER_PROMPT.format(
            chapter_number=chapter_number,
            chapter_content=chapter_content,
            character_table=self.context.get_character_table(),
            recent_summaries=self.context.get_recent_summaries(),
            foreshadowing_table=self.context.get_foreshadowing_table(),
            world_rules=json.dumps(self.state.get_world_rules(), ensure_ascii=False, indent=2),
        )

        resp = self.client.chat_with_retry(
            system_prompt=EDITOR_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,  # 审核用低温度，保持一致性
            max_tokens=4096,
        )

        result = self._parse_json_response(resp)
        result["chapter_number"] = chapter_number

        # 打印审核结果
        verdict_emoji = {"PASS": "[OK]", "PASS_WITH_WARNINGS": "[WARN]", "FAIL": "[FAIL]"}
        emoji = verdict_emoji.get(result.get("verdict", ""), "[?]")
        print(f"[Editor] 第 {chapter_number} 章: {emoji} 评分 {result.get('overall_score', 0)}/10")

        # 打印问题
        issues_found = 0
        for dim_name, dim_data in result.get("dimensions", {}).items():
            for issue in dim_data.get("issues", []):
                issues_found += 1
                if issues_found <= 5:  # 最多显示 5 个问题
                    print(f"  [{issue.get('severity', '?')}] {issue.get('description', '')[:80]}")

        if issues_found > 5:
            print(f"  ... 还有 {issues_found - 5} 个问题")

        return result

    def review_batch(self, chapters: list[dict]) -> dict:
        """
        审核一批章节

        Args:
            chapters: [{chapter_number, content}, ...]

        Returns:
            {
                batch_verdict: PASS / PASS_WITH_WARNINGS / FAIL,
                batch_score: float (平均分),
                chapter_reviews: [{...}, ...],
                summary: str
            }
        """
        print(f"\n{'='*60}")
        print(f"[Editor] 开始审核批次 ({len(chapters)} 章)")

        reviews = []
        for ch in chapters:
            review = self.review_chapter(ch["chapter_number"], ch["content"])
            reviews.append(review)

        # 汇总
        scores = [r.get("overall_score", 0) for r in reviews]
        avg_score = sum(scores) / len(scores) if scores else 0

        verdicts = [r.get("verdict", "FAIL") for r in reviews]
        if "FAIL" in verdicts:
            batch_verdict = "FAIL"
        elif "PASS_WITH_WARNINGS" in verdicts:
            batch_verdict = "PASS_WITH_WARNINGS"
        else:
            batch_verdict = "PASS"

        print(f"\n[Editor] 批次审核完成:")
        print(f"  平均分: {avg_score:.1f}/10")
        print(f"  判定: {batch_verdict}")
        print(f"  PASS: {verdicts.count('PASS')}, WARN: {verdicts.count('PASS_WITH_WARNINGS')}, FAIL: {verdicts.count('FAIL')}")

        return {
            "batch_verdict": batch_verdict,
            "batch_score": round(avg_score, 1),
            "chapter_reviews": reviews,
            "summary": f"审核 {len(chapters)} 章，平均分 {avg_score:.1f}，判定 {batch_verdict}",
        }

    def get_revision_feedback(self, chapter_number: int, review: dict) -> str:
        """
        根据审核结果生成修改建议，供 AI Writer 重写用
        """
        issues = []
        for dim_name, dim_data in review.get("dimensions", {}).items():
            for issue in dim_data.get("issues", []):
                severity = issue.get("severity", "")
                desc = issue.get("description", "")
                suggestion = issue.get("suggestion", "")
                issues.append(f"[{severity}] {desc}\n  建议: {suggestion}")

        feedback = f"""以下是第 {chapter_number} 章的修改建议：

审核评分：{review.get('overall_score', 0)}/10
判定：{review.get('verdict', 'FAIL')}

发现的问题：
{chr(10).join(issues)}

总体意见：
{review.get('summary', '')}

请在重写时逐一解决以上问题，特别是 CRITICAL 级别的问题必须全部修复。"""

        return feedback

    def update_state_from_review(self, review: dict):
        """根据审核结果更新小说状态"""
        ch_num = review.get("chapter_number")

        # 提取关键事件
        for event in review.get("key_events_extracted", []):
            print(f"[Editor] 第 {ch_num} 章关键事件: {event}")

        # 添加新人物
        for char in review.get("new_characters", []):
            print(f"[Editor] 第 {ch_num} 章新人物: {char}")

        # 更新伏笔状态
        for fs in review.get("new_foreshadowing", []):
            self.state.add_foreshadowing(
                content=str(fs),
                planted_chapter=ch_num,
            )

        for fs in review.get("resolved_foreshadowing", []):
            self.state.resolve_foreshadowing(
                content=str(fs),
                resolved_chapter=ch_num,
            )

        # 更新人物状态变化
        for change in review.get("character_state_changes", []):
            print(f"[Editor] 人物状态变化: {change}")

    @staticmethod
    def _parse_json_response(resp: str) -> dict:
        """解析 AI 返回的 JSON"""
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', resp, re.DOTALL)
        if m:
            resp = m.group(1)
        try:
            return json.loads(resp)
        except json.JSONDecodeError:
            start = resp.find('{')
            end = resp.rfind('}')
            if start >= 0 and end > start:
                return json.loads(resp[start:end + 1])
            raise RuntimeError(f"无法解析编辑审核 JSON: {resp[:500]}")
