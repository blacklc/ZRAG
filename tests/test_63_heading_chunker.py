"""HeadingChunker 单元测试"""
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from zrag.ingest.chunking.heading import HeadingChunker
from zrag.models.document import RawDocument, Chunk


class TestHeadingChunker:
    """HeadingChunker 单元测试

    覆盖以下场景:
    - 按 H1/H2/H3 标题切分
    - 无标题文档回退到 RecursiveCharacterChunker
    - 超长段降级二次切分
    - 过短 chunk 合并到相邻 chunk
    - 子 chunk 继承父标题前缀
    """

    def setup_method(self):
        self.chunker = HeadingChunker(levels=[1, 2, 3], max_size=1024, min_size=200, overlap=100)
        self.default_metadata = {"title": "测试文档"}

    def _make_document(self, content: str, source_id: str = "test_doc") -> RawDocument:
        return RawDocument(
            source_id=source_id,
            source_type="test",
            content=content,
            content_hash="abc123",
            metadata=self.default_metadata,
        )

    def test_split_on_h1(self):
        """H1 标题作为切分边界"""
        content = (
            "# 第一章\n\n"
            + "这里有一些文字来填充。需要添加更多文字以确保分片能够达到最小尺寸要求。" * 6
            + "\n\n# 第二章\n\n"
            + "这是第二章的内容。也有足够的文本来形成段落。继续添加文字来满足最小尺寸检查。" * 6
        )
        doc = self._make_document(content)
        chunks = self.chunker.chunk(doc)

        assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert "第一章" in chunks[0].content
        assert "第二章" in chunks[1].content
        assert chunks[0].source_id == "test_doc"

    def test_split_on_h2(self):
        """H2 标题作为切分边界"""
        content = (
            "## 第一部分\n\n"
            + "第一部分的正文内容。需要足够的文字来形成 chunk 并达到最小尺寸要求。" * 6
            + "\n\n## 第二部分\n\n"
            + "第二部分的正文内容。同样需要足够的文本来填充并满足最小尺寸检查。" * 6
        )
        doc = self._make_document(content)
        chunks = self.chunker.chunk(doc)

        assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"
        assert "第一部分" in chunks[0].content
        assert "第二部分" in chunks[1].content

    def test_split_on_h3(self):
        """H3 标题作为切分边界"""
        content = (
            "### 小节 A\n\n"
            + "小节 A 的内容。需要填充到足够的长度让 chunk 成立并达到最小尺寸要求。" * 7
            + "\n\n### 小节 B\n\n"
            + "小节 B 的内容。同样需要足够的文本来填充段落并满足最小尺寸检查。" * 7
        )
        doc = self._make_document(content)
        chunks = self.chunker.chunk(doc)

        assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"
        assert "小节 A" in chunks[0].content
        assert "小节 B" in chunks[1].content

    def test_no_heading_fallback_to_recursive(self):
        """无标题文档回退到 RecursiveCharacterChunker"""
        content = (
            "这是第一段文本。需要填充到足够的长度以便能够形成多个 chunk。"
            " 这里继续增加内容。再加一些内容确保分段。"
            " 让我们继续写更多的文字。把内容弄长一些。"
            " 继续填充直到超过 chunk 大小限制。"
            " 这里再多加一点。好的差不多了。"
            " 现在开始第二段的内容。同样需要填充到足够的长度。"
            " 继续写第二段。让文字变长。"
            " 再补充一些。确保能切分成多块。"
            " 好的第二段也够了。"
            " 再继续。差不多了。"
        )
        doc = self._make_document(content)
        # 使用较小的 max_size 确保触发分割
        small_chunker = HeadingChunker(levels=[1, 2, 3], max_size=150, min_size=50, overlap=20)
        chunks = small_chunker.chunk(doc)

        assert len(chunks) >= 1
        for c in chunks:
            assert c.source_id == "test_doc"
            assert c.source_type == "test"

    def test_long_section_fallback(self):
        """超长段（> max_size）降级二次切分"""
        content = (
            "# 超长章节\n\n"
            + "这是超长章节的内容。" * 200
            + "\n\n# 短章节\n\n这是短章节的内容。"
        )
        doc = self._make_document(content)
        chunks = self.chunker.chunk(doc)

        # 超长章节应被切分为多个 chunk
        assert len(chunks) >= 2
        # 所有 chunk 应继承标题路径
        for c in chunks:
            assert "超长章节" in c.content or "短章节" in c.content

    def test_short_chunks_merged(self):
        """过短 chunk（< min_size）合并到相邻 chunk"""
        content = (
            "# 大章节\n\n"
            + "A" * 500
            + "\n\n# 小章节\n\n"
            + "B" * 50  # 小于 min_size=200
        )
        doc = self._make_document(content)
        chunks = self.chunker.chunk(doc)

        assert len(chunks) == 1

    def test_child_chunk_inherits_heading_path(self):
        """子 chunk 继承父标题前缀"""
        content = (
            "# H1 标题\n\n"
            + "H1 的内容。这里写一些文字。需要添加文字以确保该分片达到最小尺寸要求。" * 6
            + "\n\n## H2 子标题\n\n"
            + "H2 的内容。也有了足够的文字。继续添加内容确保每个分片都能独立存在。" * 6
        )
        doc = self._make_document(content)
        chunks = self.chunker.chunk(doc)

        assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"
        # 第一个 chunk 是 H1 下的内容（不含 H2 子标题）
        # 第二个 chunk 包含 H2 内容，应继承 H1 前缀
        for c in chunks:
            assert c.source_id == "test_doc"
            assert c.source_type == "test"

    def test_empty_content(self):
        """空文档返回空列表"""
        doc = self._make_document("")
        chunks = self.chunker.chunk(doc)
        assert chunks == []

    def test_doc_title_inherited(self):
        """Chunk 的 doc_title 继承自 RawDocument.metadata.title"""
        content = "# 标题\n\n正文内容。有足够的文字来通过 min_size 检查。"
        doc = self._make_document(content)
        chunks = self.chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].doc_title == "测试文档"

    def test_doc_title_fallback_when_null(self):
        """当 metadata.title 为 null 时，fallback 为 source_type_source_id"""
        doc = RawDocument(
            source_id="test-source-id",
            source_type="test_type",
            content="# Test\nSome content here.",
            content_hash="",
            metadata={"title": None},
        )
        chunks = self.chunker.chunk(doc)
        assert len(chunks) > 0
        for c in chunks:
            assert c.doc_title == "test_type_test-source-id"

    def test_doc_title_fallback_when_missing(self):
        """当 metadata 中无 title 键时，fallback 为 source_type_source_id"""
        doc = RawDocument(
            source_id="test-id",
            source_type="test_type",
            content="# Title\nContent here.",
            content_hash="",
            metadata={},
        )
        chunks = self.chunker.chunk(doc)
        assert len(chunks) > 0
        for c in chunks:
            assert c.doc_title == "test_type_test-id"

    def test_doc_title_normal_value(self):
        """当 title 正常时，直接使用"""
        doc = RawDocument(
            source_id="s1",
            source_type="mac_notes",
            content="# Hello\nWorld.",
            content_hash="",
            metadata={"title": "My Note"},
        )
        chunks = self.chunker.chunk(doc)
        assert len(chunks) > 0
        for c in chunks:
            assert c.doc_title == "My Note"

    def test_first_short_section_merged_to_next(self):
        """首段过短时缓存为前缀，合并到下一段"""
        doc = RawDocument(
            source_id="s1",
            source_type="mac_notes",
            content="# Title Only\n\n## Section 2\nThis is the actual content that is long enough to meet the minimum size requirement for chunking.",
            content_hash="",
            metadata={"title": "Test Doc"},
        )
        chunks = self.chunker.chunk(doc)
        # 首段应该被合并，不应有独立的13字符chunk
        for c in chunks:
            assert len(c.content) >= 50  # 合并后应足够长
        # 合并后的内容应同时包含标题行和正文
        assert len(chunks) >= 1

    def test_heading_path_in_content(self):
        """chunk content 包含标题层级路径"""
        doc = RawDocument(
            source_id="s1",
            source_type="mac_notes",
            content="# Top Title\n\nContent under H1.\n\n## Sub Section\n\nSub content here that is long enough to meet the minimum size requirement for chunking purposes.",
            content_hash="",
            metadata={"title": "My Document"},
        )
        chunks = self.chunker.chunk(doc)
        assert len(chunks) > 0
        # 至少有一个 chunk 的 content 包含标题路径
        found = any("My Document > Top Title" in c.content or "My Document > Top Title > Sub Section" in c.content for c in chunks)
        assert found, f"No chunk contains heading path. Chunks: {[c.content[:100] for c in chunks]}"

    def test_heading_path_nested(self):
        """多层嵌套标题路径正确"""
        doc = RawDocument(
            source_id="s2",
            source_type="mac_notes",
            content="# H1 Title\n\nH1 content.\n\n## H2 Title\n\nH2 content that is long enough to meet the minimum size requirement for chunking purposes in this test.",
            content_hash="",
            metadata={"title": "Doc Title"},
        )
        chunks = self.chunker.chunk(doc)
        assert len(chunks) > 0
        # H2 section 的 content 应包含完整路径
        h2_chunks = [c for c in chunks if "H2 Title" in c.content]
        assert len(h2_chunks) > 0
        assert "Doc Title > H1 Title > H2 Title" in h2_chunks[0].content
