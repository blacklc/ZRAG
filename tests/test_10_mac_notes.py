"""测试切片 9 — MacNotesSource"""
import hashlib
import subprocess
from unittest.mock import patch

import pytest

from zrag.ingest.sources.mac_notes import MacNotesSource
from zrag.models.document import RawDocument


class TestMacNotesSource:
    """MacNotesSource 测试

    使用 unittest.mock.patch 模拟 AppleScript 调用, 不依赖真实的 Notes.app。
    """

    def test_source_type(self):
        """source_type 应返回 'mac_notes'"""
        source = MacNotesSource()
        assert source.source_type == "mac_notes"

    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_fetch_batch_returns_raw_documents(self, mock_check_output):
        """fetch_batch 应返回 RawDocument 列表"""
        # 模拟 osascript: 获取文件夹列表
        mock_check_output.side_effect = [
            "备忘录, 待办事项",   # _get_all_folders -> 两个文件夹
            "NOTE:111, NOTE:222",  # folder "备忘录" 中的 note id 列表
            "会议记录",            # _get_note_name for NOTE:111
            "日程安排",            # _get_note_name for NOTE:222
            "<div><b>会议记录内容</b></div>",  # _get_note_content for NOTE:111
            "<div><b>日程安排内容</b></div>",  # _get_note_content for NOTE:222
            "NOTE:333, NOTE:444",  # folder "待办事项" 中的 note id 列表
            "购物清单",            # _get_note_name for NOTE:333
            "工作任务",            # _get_note_name for NOTE:444
            "<div>购物清单内容</div>",  # _get_note_content for NOTE:333
            "<div>工作任务内容</div>",  # _get_note_content for NOTE:444
        ]

        source = MacNotesSource()
        batches = list(source.fetch_batch(batch_size=10))

        # 应有一个批次, 包含 4 条 RawDocument
        assert len(batches) == 1
        batch = batches[0]
        assert len(batch) == 4

        for doc in batch:
            assert isinstance(doc, RawDocument)
            assert doc.source_type == "mac_notes"
            assert doc.source_id.startswith("NOTE:")
            assert doc.content_hash == hashlib.sha256(
                doc.content.encode("utf-8")
            ).hexdigest()
            assert "folder" in doc.metadata
            assert "name" in doc.metadata

        # 验证第一条备忘录
        assert batch[0].source_id == "NOTE:111"
        assert batch[0].metadata["name"] == "会议记录"
        assert batch[0].metadata["folder"] == "备忘录"

        # 验证第三条备忘录（第二个文件夹）
        assert batch[2].source_id == "NOTE:333"
        assert batch[2].metadata["folder"] == "待办事项"

    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_fetch_batch_single_folder(self, mock_check_output):
        """指定 folder_name 时应只获取该文件夹的备忘录"""
        mock_check_output.side_effect = [
            # _get_notes_in_folder("备忘录") -> id 列表
            "NOTE:111, NOTE:222",
            "会议记录",      # _get_note_name for NOTE:111
            "日程安排",      # _get_note_name for NOTE:222
            "<div>内容1</div>",  # _get_note_content for NOTE:111
            "<div>内容2</div>",  # _get_note_content for NOTE:222
        ]

        source = MacNotesSource(folder_name="备忘录")
        batches = list(source.fetch_batch(batch_size=10))

        assert len(batches) == 1
        assert len(batches[0]) == 2
        assert batches[0][0].metadata["folder"] == "备忘录"

    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_full_sync_mode(self, mock_check_output):
        """full_sync=True 时应获取所有文件夹的备忘录"""
        mock_check_output.side_effect = [
            "备忘录, 待办事项, 个人",  # _get_all_folders
            "NOTE:111",                # notes in "备忘录"
            "会议记录",                 # _get_note_name for NOTE:111
            "<div>内容1</div>",         # _get_note_content for NOTE:111
            "NOTE:222",                # notes in "待办事项"
            "日程安排",                 # _get_note_name for NOTE:222
            "<div>内容2</div>",         # _get_note_content for NOTE:222
            "NOTE:333",                # notes in "个人"
            "个人笔记",                 # _get_note_name for NOTE:333
            "<div>内容3</div>",         # _get_note_content for NOTE:333
        ]

        source = MacNotesSource(full_sync=True)
        batches = list(source.fetch_batch(batch_size=10))

        assert len(batches) == 1
        assert len(batches[0]) == 3

        # 所有三个文件夹都应被遍历
        folders = {doc.metadata["folder"] for doc in batches[0]}
        assert folders == {"备忘录", "待办事项", "个人"}

    def test_html_to_markdown_removes_tags(self):
        """<b>text</b> 应转换为 **text**"""
        source = MacNotesSource()

        # <b> 标签
        assert source._html_to_markdown("<b>hello</b>") == "**hello**"

        # <strong> 标签
        assert source._html_to_markdown("<strong>world</strong>") == "**world**"

        # <i> 标签
        assert source._html_to_markdown("<i>italic</i>") == "*italic*"

        # <em> 标签
        assert source._html_to_markdown("<em>emphasized</em>") == "*emphasized*"

    def test_html_to_markdown_links(self):
        """<a href="url">text</a> 应转换为 [text](url)"""
        source = MacNotesSource()

        result = source._html_to_markdown(
            '<a href="https://example.com">click here</a>'
        )
        assert result == "[click here](https://example.com)"

    def test_html_to_markdown_headings(self):
        """<h1>title</h1> 应转换为 # title"""
        source = MacNotesSource()

        assert source._html_to_markdown("<h1>Title 1</h1>") == "# Title 1"
        assert source._html_to_markdown("<h2>Title 2</h2>") == "## Title 2"
        assert source._html_to_markdown("<h3>Title 3</h3>") == "### Title 3"
        assert source._html_to_markdown("<h6>Title 6</h6>") == "###### Title 6"

    def test_html_to_markdown_line_breaks(self):
        """<div> 和 <br> 应转换为换行"""
        source = MacNotesSource()

        result = source._html_to_markdown("line1<br>line2")
        assert result == "line1\nline2"

        result = source._html_to_markdown("<div>block1</div><div>block2</div>")
        # <div> 和 </div> 都会替换为 \n, 因此会出现双换行
        assert "block1" in result
        assert "block2" in result

        result = source._html_to_markdown("<p>paragraph1</p><p>paragraph2</p>")
        # <p> 和 </p> 都会替换为 \n, 因此会出现双换行
        assert "paragraph1" in result
        assert "paragraph2" in result

    def test_html_to_markdown_complex_html(self):
        """复杂 HTML 转换"""
        source = MacNotesSource()

        html = """
        <h1>Meeting Notes</h1>
        <div>
            <p><b>Date:</b> 2024-01-15</p>
            <p><i>Attendees:</i> Alice, Bob</p>
            <p>See <a href="https://docs.example.com">documentation</a> for details.</p>
        </div>
        """

        result = source._html_to_markdown(html)

        assert "# Meeting Notes" in result
        assert "**Date:**" in result
        assert "*Attendees:*" in result
        assert "[documentation](https://docs.example.com)" in result

    def test_content_hash(self):
        """相同内容应返回相同的哈希值"""
        source = MacNotesSource()

        content = "Hello, World!"
        hash1 = source._compute_hash(content)
        hash2 = source._compute_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 十六进制长度

        # 不同内容应返回不同的哈希值
        hash3 = source._compute_hash("Different content")
        assert hash1 != hash3

    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_fetch_batch_batch_size(self, mock_check_output):
        """验证 batch_size 参数生效"""
        mock_check_output.side_effect = [
            "备忘录",              # _get_all_folders
            "NOTE:1, NOTE:2, NOTE:3, NOTE:4, NOTE:5",  # notes in "备忘录"
            "n1", "n2", "n3", "n4", "n5",  # _get_note_name for each
            "<div>1</div>",        # _get_note_content for each
            "<div>2</div>",
            "<div>3</div>",
            "<div>4</div>",
            "<div>5</div>",
        ]

        source = MacNotesSource()
        batches = list(source.fetch_batch(batch_size=2))

        assert len(batches) == 3  # 5 个文档, batch_size=2 -> 3 个批次
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_get_note_content_failure(self, mock_check_output):
        """获取备忘录内容失败时应跳过该条备忘录"""
        mock_check_output.side_effect = [
            "备忘录",
            "NOTE:111, NOTE:222",
            "笔记A",              # _get_note_name for NOTE:111
            "笔记B",              # _get_note_name for NOTE:222
            "<div>内容A</div>",    # _get_note_content for NOTE:111
            subprocess.CalledProcessError(1, "osascript"),  # _get_note_content for NOTE:222 失败
        ]

        source = MacNotesSource()
        batches = list(source.fetch_batch())

        assert len(batches) == 1
        assert len(batches[0]) == 1
        assert batches[0][0].source_id == "NOTE:111"
        assert batches[0][0].metadata["name"] == "笔记A"

    def test_empty_html_to_markdown(self):
        """空 HTML 字符串应返回空字符串"""
        source = MacNotesSource()
        assert source._html_to_markdown("") == ""
