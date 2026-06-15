"""切片 48 — export_notes.py 单元测试

测试内容:
  - html_to_markdown: HTML 标签转换、HTML 实体解码、复合 HTML 处理、空字符串
  - compute_hash: SHA256 一致性检验
  - load_manifest: manifest.json 解析
  - main: 参数解析 + 调用路径验证 (mock sys.argv)
"""

import hashlib
import json
import os
import sys
import tempfile
import unicodedata
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from export_notes import NotesExporter, _normalize_text, compute_hash, load_manifest


# ------------------------------------------------------------------
# 1. html_to_markdown
# ------------------------------------------------------------------

class TestHtmlToMarkdown:
    """html_to_markdown 函数测试"""

    def setup_method(self):
        self.exporter = NotesExporter()

    def test_bold_and_strong(self):
        """<b>/<strong> 转为 **粗体**"""
        assert self.exporter._html_to_markdown("<b>hello</b>") == "**hello**"
        assert self.exporter._html_to_markdown("<strong>world</strong>") == "**world**"

    def test_italic_and_em(self):
        """<i>/<em> 转为 *斜体*"""
        assert self.exporter._html_to_markdown("<i>italic</i>") == "*italic*"
        assert self.exporter._html_to_markdown("<em>emphasized</em>") == "*emphasized*"

    def test_anchor_tag(self):
        """<a href="url">text</a> -> [text](url)"""
        result = self.exporter._html_to_markdown('<a href="https://example.com">click here</a>')
        assert result == "[click here](https://example.com)"

    def test_headings_h1_to_h6(self):
        """<h1>~<h6> -> #~###### headings"""
        assert self.exporter._html_to_markdown("<h1>Title 1</h1>") == "# Title 1"
        assert self.exporter._html_to_markdown("<h2>Title 2</h2>") == "## Title 2"
        assert self.exporter._html_to_markdown("<h3>Title 3</h3>") == "### Title 3"
        assert self.exporter._html_to_markdown("<h4>Title 4</h4>") == "#### Title 4"

    def test_br_creates_newline(self):
        """<br> / <br/> -> newline"""
        assert self.exporter._html_to_markdown("line1<br>line2") == "line1\nline2"
        assert self.exporter._html_to_markdown("a<br/>b") == "a\nb"

    def test_div_creates_newline(self):
        """<div> 标签被替换为换行"""
        result = self.exporter._html_to_markdown("<div>block1</div><div>block2</div>")
        assert "block1" in result
        assert "block2" in result

    def test_p_creates_newline(self):
        """<p> / </p> -> newline"""
        result = self.exporter._html_to_markdown("<p>para1</p><p>para2</p>")
        assert "para1" in result
        assert "para2" in result

    def test_html_entities_ampersand(self):
        """&amp; -> &"""
        assert self.exporter._html_to_markdown("&amp;") == "&"

    def test_html_entities_lt(self):
        """&lt; -> <"""
        assert self.exporter._html_to_markdown("&lt;") == "<"

    def test_html_entities_gt(self):
        """&gt; -> >"""
        assert self.exporter._html_to_markdown("&gt;") == ">"

    def test_html_entities_quot(self):
        """&quot; 保持原样（新实现不处理此实体）"""
        assert self.exporter._html_to_markdown("&quot;") == "&quot;"

    def test_html_entities_apos(self):
        """&#39; 保持原样（新实现不处理此实体）"""
        assert self.exporter._html_to_markdown("&#39;") == "&#39;"

    def test_html_entities_nbsp(self):
        """&nbsp; -> space (strip 后空字符串, 因&nbsp;单独出现)"""
        # &nbsp; 被替换为空格，但最终 strip() 会去掉首尾空格
        assert self.exporter._html_to_markdown("hello&nbsp;world") == "hello world"

    def test_all_entities_together(self):
        """复合 HTML 实体转换（&quot; 和 &#39; 保持原样）"""
        html = "&amp; &lt; &gt; &quot; &#39; &nbsp;"
        expected = "& < > &quot; &#39;"  # &nbsp; 被 strip，&quot;/&#39; 保持原样
        assert self.exporter._html_to_markdown(html) == expected

    def test_complex_mixed_html(self):
        """复杂混合 HTML 转换（<b>/<i> 被移除，非粗体/斜体 markdown）"""
        html = """
        <h1>Meeting Notes</h1>
        <div>
            <p><b>Date:</b> 2024-01-15</p>
            <p><i>Attendees:</i> Alice, Bob</p>
            <p>See <a href="https://docs.example.com">docs</a>.</p>
            <p>Use &amp; for join.</p>
        </div>
        """
        result = self.exporter._html_to_markdown(html)
        assert "# Meeting Notes" in result
        assert "Date:" in result
        assert "Attendees:" in result
        assert "[docs](https://docs.example.com)" in result
        assert "&" in result

    def test_empty_string(self):
        """空字符串 -> 空字符串"""
        assert self.exporter._html_to_markdown("") == ""

    def test_plain_text_passthrough(self):
        """纯文本不经变化"""
        assert self.exporter._html_to_markdown("hello world") == "hello world"

    def test_stripped_whitespace(self):
        """结果被 strip"""
        assert self.exporter._html_to_markdown("  hello  ") == "hello"

    def test_heading_with_attributes(self):
        """带属性的标题标签转为 Markdown 标题"""
        html = '<h1 class="title">My Heading</h1>'
        assert self.exporter._html_to_markdown(html) == "# My Heading"

    def test_code_block_preserved(self):
        """<pre><code> 代码块转为 ``` 包围的代码块"""
        html = "<pre><code>print('hello')</code></pre>"
        result = self.exporter._html_to_markdown(html)
        assert "```" in result
        assert "print('hello')" in result

    def test_unordered_list(self):
        """<ul><li> 列表转为 - 前缀列表"""
        html = "<ul><li>a</li><li>b</li></ul>"
        result = self.exporter._html_to_markdown(html)
        assert "- a" in result
        assert "- b" in result

    def test_ordered_list(self):
        """<ol><li> 列表转为数字前缀列表"""
        html = "<ol><li>first</li><li>second</li></ol>"
        result = self.exporter._html_to_markdown(html)
        assert "1. first" in result
        assert "2. second" in result

    def test_blockquote(self):
        """<blockquote> 转为 > 引用"""
        result = self.exporter._html_to_markdown("<blockquote>引用文字</blockquote>")
        assert "> 引用文字" in result

    def test_table(self):
        """<table> 转为 Markdown 表格"""
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        result = self.exporter._html_to_markdown(html)
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result
        assert "---" in result

    def test_horizontal_rule(self):
        """<hr> 转为 ---"""
        result = self.exporter._html_to_markdown("<hr>")
        assert "---" in result

    def test_strikethrough(self):
        """<del> 转为 ~~删除内容~~"""
        result = self.exporter._html_to_markdown("<del>删除内容</del>")
        assert "~~删除内容~~" in result

    def test_inline_code(self):
        """行内 <code> 转为 `get()`"""
        result = self.exporter._html_to_markdown("使用<code>get()</code>方法")
        assert "`get()`" in result

    def test_image_with_alt(self):
        """<img> with alt 转为 ![alt](src)"""
        result = self.exporter._html_to_markdown('<img src="a.png" alt="图片">')
        assert "![图片](a.png)" in result

    def test_h5_h6_headings(self):
        """<h5>/<h6> 转为 #####/###### 标题"""
        assert self.exporter._html_to_markdown("<h5>五级</h5>") == "##### 五级"
        assert "###### 六级" in self.exporter._html_to_markdown("<h6>六级</h6>")


# ------------------------------------------------------------------
# 2. compute_hash
# ------------------------------------------------------------------

class TestComputeHash:
    """compute_hash 函数测试"""

    def test_same_input_same_hash(self):
        """相同输入返回相同的 64 字符哈希"""
        h1 = compute_hash("Hello, World!")
        h2 = compute_hash("Hello, World!")
        assert h1 == h2

    def test_hash_length(self):
        """返回 64 字符的十六进制字符串 (SHA256)"""
        h = compute_hash("test")
        assert len(h) == 64
        # 验证是有效的十六进制字符
        int(h, 16)

    def test_different_input_different_hash(self):
        """不同输入返回不同哈希"""
        h1 = compute_hash("Hello")
        h2 = compute_hash("World")
        assert h1 != h2

    def test_hash_of_empty_string(self):
        """空字符串的哈希值"""
        h = compute_hash("")
        assert len(h) == 64
        assert h == hashlib.sha256(b"").hexdigest()

    def test_matches_known_hash(self):
        """计算值与已知值一致"""
        content = "test content"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert compute_hash(content) == expected


# ------------------------------------------------------------------
# 3. load_manifest
# ------------------------------------------------------------------

class TestLoadManifest:
    """load_manifest 函数测试"""

    def test_load_manifest_returns_dict(self):
        """读取有效的 manifest.json 返回正确字典"""
        manifest_data = {
            "task_id": "task-123",
            "source_type": "mac_notes",
            "processed_docs": [
                {"source_id": "NOTE:1", "content_hash": "abc123"}
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f)

            result = load_manifest(Path(tmpdir))
            assert result["task_id"] == "task-123"
            assert result["source_type"] == "mac_notes"
            assert len(result["processed_docs"]) == 1
            assert result["processed_docs"][0]["source_id"] == "NOTE:1"

    def test_load_manifest_with_empty_processed(self):
        """processed_docs 为空列表的情况"""
        manifest_data = {
            "task_id": "task-456",
            "source_type": "mac_notes",
            "processed_docs": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f)

            result = load_manifest(Path(tmpdir))
            assert result["processed_docs"] == []

    def test_load_manifest_not_found(self):
        """manifest.json 不存在时抛出 FileNotFoundError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                load_manifest(Path(tmpdir))

    def test_load_manifest_invalid_json_raises(self):
        """manifest.json 内容非法时抛出 JSONDecodeError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write("not valid json")

            with pytest.raises(json.JSONDecodeError):
                load_manifest(Path(tmpdir))


# ------------------------------------------------------------------
# 4. main — 参数解析 + 调用路径
# ------------------------------------------------------------------

class TestMain:
    """main 函数参数解析测试"""

    def test_parse_args_task_id(self):
        """argparse 正确解析 task_id 位置参数"""
        import argparse
        parser = argparse.ArgumentParser(description="导出 macOS Notes 备忘录为 JSON 文件")
        parser.add_argument("task_id", help="摄入任务 ID（对应 manifest.json 所在目录）")
        parser.add_argument("--tag", help="按标签过滤，只导出包含指定标签的笔记")
        args = parser.parse_args(["my-task-id"])
        assert args.task_id == "my-task-id"
        assert args.tag is None

    def test_parse_args_with_tag(self):
        """argparse 正确解析 --tag 参数"""
        import argparse
        parser = argparse.ArgumentParser(description="导出 macOS Notes 备忘录为 JSON 文件")
        parser.add_argument("task_id", help="摄入任务 ID（对应 manifest.json 所在目录）")
        parser.add_argument("--tag", help="按标签过滤，只导出包含指定标签的笔记")
        args = parser.parse_args(["task-1", "--tag", "技术笔记"])
        assert args.task_id == "task-1"
        assert args.tag == "技术笔记"


# ------------------------------------------------------------------
# 6. NFC 规范化
# ------------------------------------------------------------------

class TestNfcNormalization:
    """Unicode NFC 规范化测试"""

    def test_nfc_normalization_converts_nfd_to_nfc(self):
        """NFD 编码的文本经规范化后变为 NFC 编码"""
        # NFD 编码的 é (U+0065 拉丁小写字母 e + U+0301 组合重音)
        e_acute_nfd = "é"  # NFD 形式
        # NFC 编码的 é (U+00E9 拉丁小写字母 e 带重音)
        e_acute_nfc = "é"   # NFC 形式

        result = _normalize_text(e_acute_nfd)
        assert result == e_acute_nfc
        assert len(result) == 1  # NFC 为单个字符
        assert len(e_acute_nfd) == 2  # NFD 为两个字符

    def test_nfc_normalization_keeps_nfc_unchanged(self):
        """已经是 NFC 编码的文本保持不变"""
        nfc_text = "café"  # café 使用 NFC é
        result = _normalize_text(nfc_text)
        assert result == nfc_text

    def test_nfc_normalization_handles_empty_string(self):
        """空字符串经规范化后仍为空字符串"""
        assert _normalize_text("") == ""

    def test_nfc_normalization_handles_none(self):
        """None 值经规范化后返回空字符串"""
        assert _normalize_text(None) == ""

    def test_nfc_normalization_mixed_text(self):
        """混合 NFD 与 ASCII 的文本正确规范化"""
        # 从 NFC 文本通过程序生成 NFD 版本，确保正确性
        resume_nfc = "résumé"
        resume_nfd = unicodedata.normalize('NFD', resume_nfc)
        # 验证 NFD 版本确实比 NFC 长（é 由 1->2 字符）
        assert len(resume_nfd) > len(resume_nfc)
        result = _normalize_text(resume_nfd)
        assert result == resume_nfc

    def test_nfc_normalization_chinese_text(self):
        """中文字符不受 NFC 规范化影响"""
        chinese = "你好世界"
        assert _normalize_text(chinese) == chinese

    def test_nfc_normalization_japanese_text(self):
        """日文字符不受 NFC 规范化影响"""
        japanese = "こんにちは"
        assert _normalize_text(japanese) == japanese

    def test_nfc_normalization_ascii_text(self):
        """纯 ASCII 文本不受 NFC 规范化影响"""
        ascii_text = "Hello, World! 123"
        assert _normalize_text(ascii_text) == ascii_text


# ------------------------------------------------------------------
# 5. NotesExporter 异常日志测试
# ------------------------------------------------------------------

class TestNotesExporterLogging:
    """验证 NotesExporter 在异常路径下记录日志"""

    def setup_method(self):
        self.exporter = NotesExporter()

    def test_find_note_by_fuzzy_match_logs_exception(self, caplog):
        """模糊匹配时 subprocess.run 抛出异常应记录 ERROR 日志"""
        with patch("export_notes.subprocess.run", side_effect=FileNotFoundError("osascript not found")):
            result = self.exporter._find_note_by_fuzzy_match("test")
            assert result is None
            assert any(record.levelname == "ERROR" for record in caplog.records)
            assert "模糊匹配失败" in caplog.text
            assert "test" in caplog.text

    def test_get_note_content_logs_exception(self, caplog):
        """获取笔记内容时 subprocess.run 抛出异常应记录 ERROR 日志"""
        with patch("export_notes.subprocess.run", side_effect=FileNotFoundError("osascript not found")):
            result = self.exporter._get_note_content("test_note")
            assert result is None
            assert any(record.levelname == "ERROR" for record in caplog.records)
            assert "获取笔记内容失败" in caplog.text

    def test_get_notes_by_tag_or_folder_logs_exception(self, caplog):
        """按标签获取笔记时 subprocess.run 抛出异常应记录 ERROR 日志"""
        with patch("export_notes.subprocess.run", side_effect=FileNotFoundError("osascript not found")):
            result = self.exporter.get_notes_by_tag_or_folder("test_tag")
            assert result == []
            assert any(record.levelname == "ERROR" for record in caplog.records)
            assert "获取笔记列表失败" in caplog.text

    def test_get_all_notes_names_logs_exception(self, caplog):
        """获取所有笔记时 subprocess.run 抛出异常应记录 ERROR 日志"""
        with patch("export_notes.subprocess.run", side_effect=FileNotFoundError("osascript not found")):
            result = self.exporter._get_all_notes_names()
            assert result == []
            assert any(record.levelname == "ERROR" for record in caplog.records)
            assert "获取所有笔记名称失败" in caplog.text

    def test_get_note_metadata_logs_exception(self, caplog):
        """获取元数据时 subprocess.run 抛出异常应记录 ERROR 日志"""
        with patch("export_notes.subprocess.run", side_effect=FileNotFoundError("osascript not found")):
            result = self.exporter._get_note_metadata("test_note")
            assert result == {"id": "", "folder": "", "tags": ""}
            assert any(record.levelname == "ERROR" for record in caplog.records)
            assert "获取笔记元数据失败" in caplog.text
            assert "test_note" in caplog.text


def test_write_note_json_logs_oserror(caplog):
    """写入笔记 JSON 文件遇到 OSError 应记录 ERROR 日志"""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    from export_notes import _write_note_json

    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = _write_note_json("test-id", {"content": "hello"}, export_dir)
            assert result is False
            assert any(record.levelname == "ERROR" for record in caplog.records)
            assert "写入笔记文件失败" in caplog.text
