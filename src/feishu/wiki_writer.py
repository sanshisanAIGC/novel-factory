"""
飞书文档同步模块
使用 docx API 创建章节文档（绕过 Wiki 空间权限）
"""
import time
from .auth import FeishuAuth


class WikiWriter:
    """飞书文档写入器，将 AI 生成的章节同步为飞书文档"""

    def __init__(self, auth: FeishuAuth, space_id: str = "",
                 parent_node_token: str = None, wiki_doc_id: str = ""):
        self.auth = auth
        self.space_id = space_id
        self.parent_node_token = parent_node_token
        self.wiki_doc_id = wiki_doc_id  # 原 Wiki 文档 ID，用于追加目录

    # ━━━━ Wiki 文档目录操作 ━━━━

    def append_to_wiki(self, chapter_num: int, chapter_title: str, doc_url: str):
        """在原 Wiki 文档末尾追加章节链接"""
        if not self.wiki_doc_id:
            print("  [Writer] 未设置 wiki_doc_id，跳过目录追加")
            return

        link_text = f"第{chapter_num}章 {chapter_title}：{doc_url}"
        block = {
            "children": [{
                "block_type": 2,  # 文本块
                "text": {
                    "elements": [
                        {"text_run": {"content": link_text}}
                    ]
                }
            }],
            "index": -1,
        }

        resp = self.auth.post(
            f"/open-apis/docx/v1/documents/{self.wiki_doc_id}/blocks/{self.wiki_doc_id}/children",
            data=block,
        )
        code = resp.get("code", -1)
        if code == 0:
            print(f"  [Writer] 已追加第{chapter_num}章链接到 Wiki")
        else:
            print(f"  [Writer] 追加 Wiki 目录失败: {resp.get('msg')}")

    def append_section_header_to_wiki(self, text: str):
        """在 Wiki 文档末尾追加一个章节标题"""
        if not self.wiki_doc_id:
            return
        import time
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            block = {
                "children": [{
                    "block_type": 2,
                    "text": {"elements": [{"text_run": {"content": line}}]}
                }],
                "index": -1,
            }
            self.auth.post(
                f"/open-apis/docx/v1/documents/{self.wiki_doc_id}/blocks/{self.wiki_doc_id}/children",
                data=block,
            )
            time.sleep(0.2)

    def create_document(self, title: str) -> str:
        """
        创建空白 docx 文档
        返回: document_id
        """
        resp = self.auth.post(
            "/open-apis/docx/v1/documents",
            data={"title": title},
        )
        code = resp.get("code", -1)
        if code != 0:
            raise RuntimeError(
                f"创建文档失败: code={code}, msg={resp.get('msg')}"
            )
        return resp.get("data", {}).get("document", {}).get("document_id", "")

    def write_content(self, document_id: str, text: str):
        """
        使用 blocks API 将纯文本写入文档
        分段写入，每批最多 50 个 block
        """
        # 删除文档默认的第一个空段落（通过先读取再清空）
        # 将文本按段落分割
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        # 创建 text blocks
        all_blocks = []
        for para in paragraphs:
            # 限制每个 block 的文本长度（飞书 text_run content 限制）
            content = para[:5000]  # 安全限制
            block = {
                "block_type": 2,  # 文本块
                "text": {
                    "elements": [
                        {"text_run": {"content": content}}
                    ]
                }
            }
            all_blocks.append(block)

        # 分批写入（每次最多 50 个 blocks）
        batch_size = 50
        for batch_start in range(0, len(all_blocks), batch_size):
            batch = all_blocks[batch_start:batch_start + batch_size]

            resp = self.auth.post(
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                data={
                    "children": batch,
                    "index": -1,  # 追加到末尾
                },
            )
            code = resp.get("code", -1)
            if code != 0:
                print(f"  [Writer] 写入第 {batch_start//batch_size + 1} 批时出错: code={code}, msg={resp.get('msg')}")
                # 尝试逐个写入
                print(f"  [Writer] 尝试逐个写入...")
                for j, block in enumerate(batch):
                    time.sleep(0.2)
                    resp2 = self.auth.post(
                        f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                        data={"children": [block], "index": -1},
                    )
                    if resp2.get("code") != 0:
                        print(f"  [Writer] block {batch_start + j} 写入失败: {resp2.get('msg')}")

            # 速率控制
            if batch_start + batch_size < len(all_blocks):
                time.sleep(0.3)

    def write_markdown_content(self, document_id: str, markdown: str):
        """兼容旧接口 — 写入 Markdown 文本"""
        self.write_content(document_id, markdown)

    def create_chapter_doc(self, chapter_num: int, title: str, content: str) -> dict:
        """
        创建单章飞书文档

        Returns:
            {success, chapter_num, document_id, url}
        """
        doc_title = f"第{chapter_num}章 {title}" if title and title != f"第{chapter_num}章" else f"第{chapter_num}章"

        # 限制标题长度
        if len(doc_title) > 100:
            doc_title = doc_title[:97] + "..."

        try:
            doc_id = self.create_document(doc_title)
            self.write_content(doc_id, content)
            url = f"https://uvc41b5racu.feishu.cn/docx/{doc_id}"
            print(f"  [Writer] 文档已创建: {doc_title}")
            print(f"  [Writer] URL: {url}")

            # 追加链接到原 Wiki 文档
            self.append_to_wiki(chapter_num, title, url)

            return {
                "success": True,
                "chapter_num": chapter_num,
                "document_id": doc_id,
                "title": doc_title,
                "url": url,
            }
        except Exception as e:
            print(f"  [Writer] 创建失败: {e}")
            return {
                "success": False,
                "chapter_num": chapter_num,
                "error": str(e),
            }

    def batch_sync_chapters(self, chapters: list[dict], batch_label: str = "") -> list[dict]:
        """
        批量同步章节到飞书文档

        Args:
            chapters: [{chapter_num, title, content}, ...]
            batch_label: 批次标签（日志用）

        Returns:
            [{success, chapter_num, document_id, url}, ...]
        """
        results = []
        total = len(chapters)

        for i, ch in enumerate(chapters):
            print(f"[Writer] 同步第 {ch['chapter_num']} 章 ({i+1}/{total})...")
            result = self.create_chapter_doc(
                ch["chapter_num"],
                ch.get("title", ""),
                ch["content"],
            )
            results.append(result)

            # 速率控制
            if i < total - 1:
                time.sleep(1.0)

        success_count = sum(1 for r in results if r.get("success"))
        print(f"[Writer] 批量同步完成: {success_count}/{total} 成功")

        return results

    # ━━━━ 兼容旧接口 ━━━━

    def create_wiki_page(self, title: str, content: str, parent_token: str = None) -> dict:
        """
        兼容旧接口 — 实际调用 docx API
        """
        result = self.create_chapter_doc(0, title, content)
        return {
            "node_token": result.get("document_id", ""),
            "obj_token": result.get("document_id", ""),
            "title": title,
            "url": result.get("url", ""),
        }

    def create_chapter_node(self, chapter_num: int, title: str, content: str) -> dict:
        """兼容旧接口"""
        return self.create_chapter_doc(chapter_num, title, content)

    def list_nodes(self, parent_token: str = None) -> list[dict]:
        """docx API 不支持列出节点，返回空"""
        return []

    def update_wiki_page(self, node_token: str, title: str, content: str):
        """更新已有文档内容"""
        self.write_markdown_content(node_token, content)
