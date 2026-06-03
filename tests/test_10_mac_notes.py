"""测试切片 9/10 — MacNotesSource"""
import hashlib
import subprocess
from unittest.mock import patch

import pytest

from zrag.ingest.sources.mac_notes import MacNotesSource
from zrag.models.document import RawDocument


def _make_raw_doc(source_id, name, content, folder="默认"):
    """创建用于 mock 的 RawDocument"""
    return RawDocument(
        source_id=source_id,
        source_type="mac_notes",
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        metadata={"folder": folder, "name": name},
    )


class TestMacNotesSource:
    """MacNotesSource 测试 — 使用 mock 模拟 AppleScript 调用"""

    def test_source_type(self):
        """source_type 应返回 'mac_notes'"""
        source = MacNotesSource()
        assert source.source_type == "mac_notes"

    @patch.object(MacNotesSource, "_get_folder_data")
    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_fetch_batch_returns_raw_documents(
        self, mock_check_output, mock_folder_data
    ):
        """fetch_batch 返回 RawDocument 列表（合并 AppleScript 模式）"""
        mock_check_output.return_value = "备忘录, 待办事项"
        mock_folder_data.side_effect = [
            [
                _make_raw_doc("NOTE:111", "会议记录", "**会议记录内容**", "备忘录"),
                _make_raw_doc("NOTE:222", "日程安排", "**日程安排内容**", "备忘录"),
            ],
            [
                _make_raw_doc("NOTE:333", "购物清单", "购物清单内容", "待办事项"),
                _make_raw_doc("NOTE:444", "工作任务", "工作任务内容", "待办事项"),
            ],
        ]

        source = MacNotesSource()
        batches = list(source.fetch_batch(batch_size=10))

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

        assert batch[0].source_id == "NOTE:111"
        assert batch[0].metadata["name"] == "会议记录"
        assert batch[0].metadata["folder"] == "备忘录"

        assert batch[2].source_id == "NOTE:333"
        assert batch[2].metadata["folder"] == "待办事项"

    @patch.object(MacNotesSource, "_get_folder_data")
    def test_fetch_batch_single_folder(self, mock_folder_data):
        """指定 folder_name 时只获取该文件夹 — 只需一次 _get_folder_data 调用"""
        mock_folder_data.return_value = [
            _make_raw_doc("NOTE:111", "会议记录", "内容1", "备忘录"),
            _make_raw_doc("NOTE:222", "日程安排", "内容2", "备忘录"),
        ]

        source = MacNotesSource(folder_name="备忘录")
        batches = list(source.fetch_batch(batch_size=10))

        mock_folder_data.assert_called_once_with("备忘录")
        assert len(batches) == 1
        assert len(batches[0]) == 2
        assert batches[0][0].metadata["folder"] == "备忘录"

    @patch.object(MacNotesSource, "_get_folder_data")
    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_full_sync_mode(self, mock_check_output, mock_folder_data):
        """full_sync=True 遍历所有文件夹"""
        mock_check_output.return_value = "备忘录, 待办事项, 个人"
        mock_folder_data.side_effect = [
            [_make_raw_doc("NOTE:111", "会议记录", "c1", "备忘录")],
            [_make_raw_doc("NOTE:222", "日程安排", "c2", "待办事项")],
            [_make_raw_doc("NOTE:333", "个人笔记", "c3", "个人")],
        ]

        source = MacNotesSource(full_sync=True)
        batches = list(source.fetch_batch(batch_size=10))

        assert len(batches) == 1
        assert len(batches[0]) == 3
        folders = {doc.metadata["folder"] for doc in batches[0]}
        assert folders == {"备忘录", "待办事项", "个人"}

    def test_html_to_markdown_removes_tags(self):
        """<b>text 转为 **text**，<i> 转为 *"""
        source = MacNotesSource()
        assert source._html_to_markdown("<b>hello</b>") == "**hello**"
        assert source._html_to_markdown("<strong>world</strong>") == "**world**"
        assert source._html_to_markdown("<i>italic</i>") == "*italic*"
        assert source._html_to_markdown("<em>emphasized</em>") == "*emphasized*"

    def test_html_to_markdown_links(self):
        """<a href> 转为 [text](url)"""
        source = MacNotesSource()
        result = source._html_to_markdown(
            '<a href="https://example.com">click here</a>'
        )
        assert result == "[click here](https://example.com)"

    def test_html_to_markdown_headings(self):
        """<h1>-<h6> 转为 #-##..."""
        source = MacNotesSource()
        assert source._html_to_markdown("<h1>T1</h1>") == "# T1"
        assert source._html_to_markdown("<h2>T2</h2>") == "## T2"
        assert source._html_to_markdown("<h3>T3</h3>") == "### T3"
        assert source._html_to_markdown("<h6>T6</h6>") == "###### T6"

    def test_html_to_markdown_line_breaks(self):
        """<div>/<br>/<p> 转行"""
        source = MacNotesSource()
        assert source._html_to_markdown("line1<br>line2") == "line1\nline2"
        result = source._html_to_markdown("<div>block1</div><div>block2</div>")
        assert "block1" in result
        assert "block2" in result

    def test_html_to_markdown_complex_html(self):
        """复杂 HTML 综合转换"""
        source = MacNotesSource()
        html = """
        <h1>Meeting Notes</h1>
        <div>
            <p><b>Date:</b> 2024-01-15</p>
            <p><i>Attendees:</i> Alice, Bob</p>
            <p>See <a href="https://docs.example.com">docs</a>.</p>
        </div>
        """
        result = source._html_to_markdown(html)
        assert "# Meeting Notes" in result
        assert "**Date:**" in result
        assert "*Attendees:*" in result
        assert "[docs](https://docs.example.com)" in result

    def test_content_hash(self):
        """相同内容返回相同 hash"""
        source = MacNotesSource()
        h1 = source._compute_hash("Hello")
        h2 = source._compute_hash("Hello")
        assert h1 == h2
        assert len(h1) == 64
        assert h1 != source._compute_hash("Different")

    @patch.object(MacNotesSource, "_get_folder_data")
    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_fetch_batch_batch_size(self, mock_check_output, mock_folder_data):
        """batch_size 参数生效 — 5 篇文档, batch_size=2 → 3 批次"""
        mock_check_output.return_value = "备忘录"
        mock_folder_data.return_value = [
            _make_raw_doc(f"NOTE:{i}", f"n{i}", f"c{i}") for i in range(1, 6)
        ]
        source = MacNotesSource()
        batches = list(source.fetch_batch(batch_size=2))
        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    @patch.object(MacNotesSource, "_get_folder_data")
    @patch("zrag.ingest.sources.mac_notes.subprocess.check_output")
    def test_get_folder_data_failure(
        self, mock_check_output, mock_folder_data
    ):
        """_get_folder_data 失败 (subprocess 异常) 时跳过该文件夹"""
        mock_check_output.return_value = "备忘录, 待办事项"
        mock_folder_data.side_effect = [
            [_make_raw_doc("NOTE:111", "正常笔记", "c1")],
            [],
        ]
        source = MacNotesSource()
        batches = list(source.fetch_batch())
        assert len(batches[0]) == 1

    def test_empty_html_to_markdown(self):
        """空 HTML → 空字符串"""
        source = MacNotesSource()
        assert source._html_to_markdown("") == ""
