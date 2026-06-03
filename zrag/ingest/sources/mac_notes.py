"""macOS 备忘录数据源实现

通过 AppleScript (osascript) 调用 macOS Notes.app, 获取备忘录内容并转换为 RawDocument。
"""

import hashlib
import re
import subprocess
from typing import Iterator

from zrag.ingest.sources.base import DocumentSource
from zrag.models.document import RawDocument


class MacNotesSource(DocumentSource):
    """macOS 备忘录数据源实现

    通过 AppleScript (osascript) 调用 macOS Notes.app, 获取备忘录内容并转换为 RawDocument。
    支持按文件夹筛选和全量同步两种模式。

    @param folder_name: 指定要导出的文件夹名称, 默认为 None 表示导出所有文件夹
    @type  folder_name: str, optional
    @param full_sync: 是否全量同步模式, 若为 True 则获取所有备忘录（忽略 folder_name）, defaults to False
    @type  full_sync: bool, optional
    """

    def __init__(self, folder_name: str | None = None, full_sync: bool = False):
        """构造方法

        @param folder_name: 指定要导出的文件夹名称, 默认为 None 表示导出所有文件夹
        @type  folder_name: str, optional
        @param full_sync: 是否全量同步模式, 若为 True 则获取所有备忘录（忽略 folder_name）, defaults to False
        @type  full_sync: bool, optional
        """
        self.folder_name = folder_name
        self.full_sync = full_sync

    def fetch_batch(self, batch_size: int = 10) -> Iterator[list[RawDocument]]:
        """分批获取备忘录

        使用合并的 AppleScript 脚本一次性获取每个文件夹内所有笔记的 ID/名称/正文。
        full_sync 模式下先获取全部文件夹列表再逐个文件夹导出。
        单文件夹模式只需一次 osascript 调用。

        @param batch_size: 每批次最大备忘录数量, defaults to 10
        @type  batch_size: int, optional

        @return: 生成器, 每次 yield 一个 RawDocument 列表
        @type:   Iterator[list[RawDocument]]

        @raises: AppleScript 调用失败
        @type:   subprocess.CalledProcessError
        """
        all_documents: list[RawDocument] = []

        if self.full_sync or self.folder_name is None:
            folders = self._get_all_folders()
        else:
            folders = [self.folder_name]

        for folder in folders:
            folder_docs = self._get_folder_data(folder)
            all_documents.extend(folder_docs)

        for i in range(0, len(all_documents), batch_size):
            yield all_documents[i:i + batch_size]

    @property
    def source_type(self) -> str:
        """获取数据源类型标识

        @return: 数据源类型字符串 "mac_notes"
        @type:   str
        """
        return "mac_notes"

    def _get_all_folders(self) -> list[str]:
        """获取所有备忘录文件夹名称列表

        通过 AppleScript 调用 Notes.app 获取所有文件夹的名称。

        @return: 所有备忘录文件夹名称列表
        @type:   list[str]

        @raises: AppleScript 调用失败
        @type:   subprocess.CalledProcessError
        """
        script = """
tell application "Notes"
    set folderList to name of folders
    return folderList
end tell
"""
        output = subprocess.check_output(
            ["osascript", "-e", script],
            text=True,
        )
        folders = [f.strip() for f in output.strip().split(", ") if f.strip()]
        return folders

    def _get_folder_data(self, folder_name: str) -> list[RawDocument]:
        """获取指定文件夹内所有备忘录的完整数据

        通过一次合并的 AppleScript 调用, 批量获取文件夹内所有笔记的 ID、名称和正文,
        避免逐条获取带来的大量 subprocess 开销。

        AppleScript 返回值格式:
          每条笔记占一行, id§§§name§§§body
        行以换行分隔。

        @param folder_name: 文件夹名称
        @type  folder_name: str

        @return: 该文件夹内所有备忘录的 RawDocument 列表
        @type:   list[RawDocument]

        @raises: AppleScript 调用失败
        @type:   subprocess.CalledProcessError
        """
        script = f"""
tell application "Notes"
    set output to ""
    repeat with n in notes of folder "{folder_name}"
        try
            set output to output & id of n & "§§§" & name of n & "§§§" & body of n & "¶¶¶"
        end try
    end repeat
    return output
end tell
"""
        try:
            output = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
            )
        except subprocess.CalledProcessError:
            return []

        documents: list[RawDocument] = []
        for entry in output.strip().split("¶¶¶"):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split("§§§", 2)
            if len(parts) != 3:
                continue
            note_id, note_name, html_body = parts
            markdown_content = self._html_to_markdown(html_body)
            content_hash = self._compute_hash(markdown_content)
            documents.append(RawDocument(
                source_id=note_id,
                source_type=self.source_type,
                content=markdown_content,
                content_hash=content_hash,
                metadata={"folder": folder_name, "name": note_name},
            ))
        return documents

    def _html_to_markdown(self, html: str) -> str:
        """将 HTML 转换为 Markdown 格式（纯正则, 无外部依赖）

        覆盖常见场景:
        - <div> → \\n（块级元素转行）
        - <br> → \\n
        - <b>/<strong> → **
        - <i>/<em> → *
        - <a href="url">text</a> → [text](url)
        - <h1>-<h6> → # 前缀
        - <p> → \\n
        - 清理多余空白字符

        @param html: 输入的 HTML 字符串
        @type  html: str

        @return: 转换后的 Markdown 字符串
        @type:   str
        """
        text = html

        # 将 <h1> ~ <h6> 转换为 Markdown 标题
        for i in range(6, 0, -1):
            pattern = re.compile(
                rf"<h{i}[^>]*>(.*?)</h{i}>", re.DOTALL | re.IGNORECASE
            )
            text = pattern.sub(r"#" * i + r" \1", text)

        # 将 <a href="url">text</a> 转换为 [text](url)
        text = re.sub(
            r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            r"[\2](\1)",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # 将 <b> 和 <strong> 转换为 **
        text = re.sub(
            r"<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>",
            r"**\1**",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # 将 <i> 和 <em> 转换为 *
        text = re.sub(
            r"<(?:i|em)[^>]*>(.*?)</(?:i|em)>",
            r"*\1*",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # 将 <br> 和 <br/> 转换为换行
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

        # 将 <div> 和 </div> 转换为换行
        text = re.sub(r"</?div[^>]*>", "\n", text, flags=re.IGNORECASE)

        # 将 <p> 和 </p> 转换为换行
        text = re.sub(r"</?p[^>]*>", "\n", text, flags=re.IGNORECASE)

        # 移除剩余的 HTML 标签
        text = re.sub(r"<[^>]+>", "", text)

        # 将 HTML 实体解码
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        text = text.replace("&nbsp;", " ")

        # 压缩多余空白字符: 将连续多个空格/换行压缩为单个换行
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        return text

    def _compute_hash(self, content: str) -> str:
        """计算内容哈希值

        使用 SHA256 对内容进行哈希计算, 用于增量同步时的内容变更检测。

        @param content: 文档内容文本
        @type  content: str

        @return: SHA256 十六进制哈希字符串
        @type:   str
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
