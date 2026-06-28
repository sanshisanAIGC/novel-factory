"""
风格提取模块
从已有章节中分析写作风格，生成风格画像 JSON
"""
import json
import re
from src.ai.prompts import STYLE_EXTRACT_PROMPT, STYLE_EXTRACT_USER_PROMPT


class StyleExtractor:
    """小说风格提取器"""

    def __init__(self, client):
        """
        Args:
            client: DeepSeekClient 实例
        """
        self.client = client

    def extract_from_text(self, text: str, max_sample_chars: int = 15000) -> dict:
        """
        从文本中提取写作风格

        Args:
            text: 小说文本
            max_sample_chars: 用于分析的文本最大字符数（控制 API 成本）

        Returns:
            风格画像 dict
        """
        # 取样：取开头 + 中间 + 结尾
        if len(text) > max_sample_chars:
            third = max_sample_chars // 3
            sample = text[:third] + "\n...\n" + text[len(text)//2 - third//2:len(text)//2 + third//2] + "\n...\n" + text[-third:]
        else:
            sample = text

        print(f"[StyleExtractor] 分析文本: {len(sample)} 字符 (原始 {len(text)} 字符)")

        user_prompt = STYLE_EXTRACT_USER_PROMPT.format(novel_text=sample)

        resp = self.client.chat_with_retry(
            system_prompt="你是一位专业的文学分析专家。请严格以 JSON 格式输出分析结果。",
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=4096,
        )

        # 解析 JSON
        profile = self._parse_json_response(resp)

        # 补充基础统计
        profile["basic_stats"] = self._compute_basic_stats(sample)

        print(f"[StyleExtractor] 风格提取完成")
        print(f"  叙事视角: {profile.get('perspective', '未知')}")
        print(f"  句长偏好: {profile.get('sentence_style', {}).get('preference', '未知')}")
        print(f"  情感基调: {profile.get('emotional_tone', {}).get('temperature', '未知')}")

        return profile

    def extract_from_chapters(self, chapters_dir) -> dict:
        """
        从章节文件目录中提取风格

        Args:
            chapters_dir: 章节文件目录 (Path)
        """
        # 读取所有章节文件
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        if not chapter_files:
            raise FileNotFoundError(f"在 {chapters_dir} 中未找到章节文件")

        print(f"[StyleExtractor] 从 {len(chapter_files)} 个章节文件中提取风格...")

        # 合并文本（取样策略：取前3章 + 中间2章 + 最后2章）
        samples = []
        indices = [0, 1, 2] if len(chapter_files) >= 3 else list(range(len(chapter_files)))
        mid = len(chapter_files) // 2
        indices += [mid, mid + 1] if mid + 1 < len(chapter_files) else []
        indices += [len(chapter_files) - 2, len(chapter_files) - 1] if len(chapter_files) >= 2 else []

        for idx in sorted(set(indices)):
            if idx < len(chapter_files):
                content = chapter_files[idx].read_text(encoding="utf-8")
                samples.append(content[:3000])  # 每章取前 3000 字

        combined = "\n\n---\n\n".join(samples)
        return self.extract_from_text(combined)

    def save_profile(self, profile: dict, filepath):
        """保存风格画像到文件"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"[StyleExtractor] 风格画像已保存: {filepath}")

    def load_profile(self, filepath) -> dict:
        """从文件加载风格画像"""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _compute_basic_stats(text: str) -> dict:
        """计算基础文本统计"""
        # 估算句长
        sentences = re.split(r'[。！？；\n]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        avg_len = sum(len(s) for s in sentences) // max(len(sentences), 1)

        # 估算段落数
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        avg_para_len = sum(len(p) for p in paragraphs) // max(len(paragraphs), 1)

        # 对话占比（粗略估计：引号内容占比）
        quoted = re.findall(r'["""][^"」""]+["」""]', text)
        quoted_chars = sum(len(q) for q in quoted)
        total_chars = len(text.replace('\n', '').replace(' ', ''))

        return {
            "avg_sentence_length": avg_len,
            "avg_paragraph_length": avg_para_len,
            "paragraph_count": len(paragraphs),
            "dialogue_char_ratio": round(quoted_chars / max(total_chars, 1), 2),
            "sample_size_chars": len(text),
        }

    @staticmethod
    def _parse_json_response(resp: str) -> dict:
        """解析 AI 返回的 JSON"""
        import re
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
            raise RuntimeError(f"无法解析风格 JSON: {resp[:500]}")
