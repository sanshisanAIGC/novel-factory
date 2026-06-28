"""
飞书 Wiki 读取模块
从飞书知识库读取小说内容
"""
import re
import json
from pathlib import Path
from .auth import FeishuAuth


class WikiReader:
    """飞书 Wiki 读取器"""

    def __init__(self, auth: FeishuAuth):
        self.auth = auth

    def resolve_wiki_token(self, wiki_token: str) -> dict:
        """
        解析 Wiki Token，获取节点信息
        返回: {title, obj_type, obj_token, space_id, node_token}
        """
        resp = self.auth.get(
            "/open-apis/wiki/v2/spaces/get_node",
            params={"token": wiki_token},
        )
        code = resp.get("code", -1)
        if code != 0:
            raise RuntimeError(
                f"无法读取 Wiki 节点: code={code}, msg={resp.get('msg')}\n"
                f"请确认：\n"
                f"1. 飞书应用已添加 wiki:node:read 权限\n"
                f"2. 机器人已被添加为 Wiki 知识空间成员\n"
                f"3. Wiki Token 正确"
            )

        node = resp.get("data", {}).get("node", {})
        return {
            "title": node.get("title", ""),
            "obj_type": node.get("obj_type", ""),
            "obj_token": node.get("obj_token", ""),
            "space_id": node.get("space_id", ""),
            "node_token": node.get("node_token", ""),
        }

    def read_document_raw(self, document_id: str) -> str:
        """读取 docx 文档的纯文本内容"""
        resp = self.auth.get(
            f"/open-apis/docx/v1/documents/{document_id}/raw_content"
        )
        code = resp.get("code", -1)
        if code != 0:
            raise RuntimeError(
                f"读取文档失败: code={code}, msg={resp.get('msg')}"
            )
        return resp.get("data", {}).get("content", "")

    def read_document_blocks(self, document_id: str) -> list[dict]:
        """读取文档的块结构（含格式信息）"""
        resp = self.auth.get(
            f"/open-apis/docx/v1/documents/{document_id}/blocks"
        )
        code = resp.get("code", -1)
        if code != 0:
            raise RuntimeError(
                f"读取文档块失败: code={code}, msg={resp.get('msg')}"
            )
        return resp.get("data", {}).get("items", [])

    def read_novel_from_wiki(self, wiki_token: str) -> dict:
        """
        从飞书 Wiki 读取完整小说
        返回: {title, content, chapters_info}
        """
        print(f"[WikiReader] 解析 Wiki Token: {wiki_token[:12]}...")
        node_info = self.resolve_wiki_token(wiki_token)
        print(f"[WikiReader] 小说标题: {node_info['title']}")
        print(f"[WikiReader] 文档类型: {node_info['obj_type']}")

        if node_info["obj_type"] != "docx":
            raise RuntimeError(
                f"不支持的文档类型: {node_info['obj_type']}，目前仅支持 docx"
            )

        print(f"[WikiReader] 读取文档内容...")
        content = self.read_document_raw(node_info["obj_token"])
        print(f"[WikiReader] 读取完成，共 {len(content)} 字符")

        # 简单分析章节结构
        chapters_info = self._analyze_chapters(content)

        return {
            "title": node_info["title"],
            "content": content,
            "chapters_info": chapters_info,
            "wiki_token": wiki_token,
            "document_id": node_info["obj_token"],
            "space_id": node_info["space_id"],
            "node_token": node_info["node_token"],
        }

    def _analyze_chapters(self, content: str) -> dict:
        """
        从文本中识别章节结构
        尝试匹配常见的章节标题模式
        """
        # 多种章节模式
        patterns = [
            r'(第[零一二三四五六七八九十百千\d]+章[^\n]*)',
            r'(第[零一二三四五六七八九十百千\d]+节[^\n]*)',
            r'(Chapter\s+\d+[^\n]*)',
            r'(^\d+[\.、]\s*[^\n]{2,30}$)',
        ]

        chapters = []
        for pattern in patterns:
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            if len(matches) >= 3:  # 至少找到3个匹配才认为是有效模式
                for m in matches:
                    chapters.append({
                        "title": m.group(1).strip(),
                        "position": m.start(),
                    })
                break

        # 按位置排序
        chapters.sort(key=lambda c: c["position"])

        return {
            "count": len(chapters) if chapters else None,
            "detected_pattern": bool(chapters),
            "chapters": chapters,
        }

    def save_to_file(self, content: str, filepath: Path):
        """保存内容到本地文件"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        print(f"[WikiReader] 内容已保存到: {filepath}")
