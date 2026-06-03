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

        通过 AppleScript 获取备忘录列表, 逐条读取内容后分批返回。
        若 full_sync 为 True 则遍历所有文件夹获取备忘录;
        否则根据 folder_name 筛选指定文件夹（folder_name 为 None 时也获取所有文件夹）。

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
            notes = self._get_notes_in_folder(folder)
            for note_id, note_name in notes:
                html_content = self._get_note_content(note_id)
                if html_content is None:
                    continue
                markdown_content = self._html_to_markdown(html_content)
                content_hash = self._compute_hash(markdown_content)
                doc = RawDocument(
                    source_id=note_id,
                    source_type=self.source_type,
                    content=markdown_content,
                    content_hash=content_hash,
                    metadata={"folder": folder, "name": note_name},
                )
                all_documents.append(doc)

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

    def _get_notes_in_folder(self, folder_name: str) -> list[tuple[str, str]]:
        """获取指定文件夹内所有备忘录的 ID 和名称

        通过 AppleScript 调用 Notes.app 获取指定文件夹中备忘录的 id 和 name。

        @param folder_name: 文件夹名称
        @type  folder_name: str

        @return: 备忘录 (id, name) 元组列表
        @type:   list[tuple[str, str]]

        @raises: AppleScript 调用失败
        @type:   subprocess.CalledProcessError
        """
        script = f"""
tell application "Notes"
    set noteList to id of notes of folder "{folder_name}"
    return noteList
end tell
"""
        try:
            output = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
            )
        except subprocess.CalledProcessError:
            return []

        ids = [n.strip() for n in output.strip().split(", ") if n.strip()]

        result = []
        for note_id in ids:
            name = self._get_note_name(note_id)
            if name is not None:
                result.append((note_id, name))
        return result

    def _get_note_name(self, note_id: str) -> str | None:
        """通过 AppleScript 获取单条备忘录的名称

        @param note_id: 备忘录 ID
        @type  note_id: str

        @return: 备忘录名称, 获取失败返回 None
        @type:   str | None
        """
        script = f"""
tell application "Notes"
    set noteName to name of note id "{note_id}"
    return noteName
end tell
"""
        try:
            output = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
            )
            return output.strip()
        except subprocess.CalledProcessError:
            return None

    def _get_note_content(self, note_id: str) -> str | None:
        """通过 AppleScript 获取单条备忘录的 HTML 内容

        @param note_id: 备忘录 ID
        @type  note_id: str

        @return: 备忘录的 HTML 内容字符串, 获取失败返回 None
        @type:   str | None
        """
        script = f"""
tell application "Notes"
    set noteContent to body of note id "{note_id}"
    return noteContent
end tell
"""
        try:
            output = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
            )
            return output
        except subprocess.CalledProcessError:
            return None

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
