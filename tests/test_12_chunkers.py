"""切片 11 — ChunkingStrategy 具体实现测试

测试内容：
  - ParagraphChunker: 段落分割、超长截断、小段落合并
  - RecursiveCharacterChunker: 递归分割、长文本拆分、重叠
  - CompositeChunker: 组合策略
  - Registry: source_type 映射与兜底
"""

import pytest

from zrag.models.document import RawDocument
from zrag.ingest.chunking.paragraph import ParagraphChunker
from zrag.ingest.chunking.recursive import RecursiveCharacterChunker
from zrag.ingest.chunking.composite import CompositeChunker
from zrag.ingest.chunking.registry import CHUNKER_REGISTRY, get_chunker


# ============================================================
# ParagraphChunker
# ============================================================

class TestParagraphChunker:
    """ParagraphChunker 行为验证"""

    def test_paragraph_chunker_simple(self):
        """段落分割, 段落数 = chunk 数"""
        chunker = ParagraphChunker(max_size=512, min_size=0)
        doc = RawDocument(
            source_id="doc_p001",
            source_type="test",
            content="第一段落内容。\n\n第二段落内容。\n\n第三段落内容。",
            content_hash="h1",
            metadata={"title": "测试文档"},
        )
        chunks = chunker.chunk(doc)
        assert len(chunks) == 3
        assert "第一段落内容。" in chunks[0].content
        assert "第二段落内容。" in chunks[1].content
        assert "第三段落内容。" in chunks[2].content
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[2].chunk_index == 2

    def test_paragraph_chunker_long_paragraph(self):
        """段落超 max_size 截断"""
        chunker = ParagraphChunker(max_size=20)
        long_para = "A" * 50
        doc = RawDocument(
            source_id="doc_p002",
            source_type="test",
            content=long_para,
            content_hash="h2",
        )
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert len(chunks[0].content) == 20
        assert chunks[0].content == "A" * 20

    def test_paragraph_chunker_min_size_merge(self):
        """小段落合并到前一个 chunk"""
        chunker = ParagraphChunker(max_size=512, min_size=10)
        doc = RawDocument(
            source_id="doc_p003",
            source_type="test",
            content="这是一个长段落的内容,长度超过最小长度。\n\n短。\n\n另一个正常段落内容。",
            content_hash="h3",
        )
        chunks = chunker.chunk(doc)
        # 第二个段落 "短。" 只有 2 个字符, 小于 min_size, 应合并到第一个段落
        assert len(chunks) == 2
        assert "短。" in chunks[0].content
        assert "另一个正常段落内容。" in chunks[1].content


# ============================================================
# RecursiveCharacterChunker
# ============================================================

class TestRecursiveCharacterChunker:
    """RecursiveCharacterChunker 行为验证"""

    def test_recursive_chunker_by_paragraph(self):
        """递归: 按段落分割不失真"""
        chunker = RecursiveCharacterChunker(max_size=20, overlap=0)
        # 每个段落长度超过 20, 确保被拆分
        doc = RawDocument(
            source_id="doc_r001",
            source_type="test",
            content="第一段落的详细内容介绍。\n\n第二段落的详细内容介绍。\n\n第三段落的详细内容介绍。",
            content_hash="hr1",
        )
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 3, f"Expected at least 3 chunks, got {len(chunks)}"
        # 验证段落边界仍在 chunk 中
        all_content = "".join(c.content for c in chunks)
        assert "第一段落的" in all_content
        assert "第二段落的" in all_content
        assert "第三段落的" in all_content

    def test_recursive_chunker_long_text(self):
        """递归: 长文本被拆分"""
        chunker = RecursiveCharacterChunker(max_size=15, overlap=0)
        # 构造一个超过 max_size 的连续文本, 通过"。"分割未能合并到 <= max_size
        text = "这是第一句。" + "这是第二句。" + "这是第三句。" + "这是第四句。" + "这是第五句。" + "这是第六句。" + "这是第七句。"
        doc = RawDocument(
            source_id="doc_r002",
            source_type="test",
            content=text,
            content_hash="hr2",
        )
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}"
        for c in chunks:
            assert len(c.content) <= 15, f"chunk too long: '{c.content}' ({len(c.content)} chars)"

    def test_recursive_chunker_overlap(self):
        """递归: overlap 生效"""
        chunker = RecursiveCharacterChunker(max_size=20, overlap=8)
        text = "第一句。" + "第二句。" + "第三句。" + "第四句。" + "第五句。" + "第六句。" + "第七句。" + "第八句。"
        doc = RawDocument(
            source_id="doc_r003",
            source_type="test",
            content=text,
            content_hash="hr3",
        )
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1, "Expected more than 1 chunk for overlap test"
        # 第二个 chunk 的开头应包含第一个 chunk 末尾的重叠字符
        prev_tail = chunks[0].content[-8:]
        assert chunks[1].content.startswith(prev_tail), (
            f"Expected overlap: '{prev_tail}' not at start of '{chunks[1].content}'"
        )


# ============================================================
# CompositeChunker
# ============================================================

class TestCompositeChunker:
    """CompositeChunker 行为验证"""

    def test_composite_chunker(self):
        """组合: 正常段落直接通过, 超长段落被递归切分"""
        chunker = CompositeChunker(max_size=20)
        text = (
            "短段落 A。\n\n"
            + "B" * 50
            + "\n\n"
            + "短段落 C。"
        )
        doc = RawDocument(
            source_id="doc_c001",
            source_type="test",
            content=text,
            content_hash="hc1",
        )
        chunks = chunker.chunk(doc)
        # 短段落 A 和 C 直接通过, 超长段落 B*50 被切分为多个 chunk
        # 至少应包含短段落 A、短段落 C 和超长段落拆出的 chunk
        assert len(chunks) >= 3
        # 所有 chunk content 不超过 max_size
        for c in chunks:
            assert len(c.content) <= 20, f"chunk content too long: {c.content}"


# ============================================================
# Registry
# ============================================================

class TestRegistry:
    """CHUNKER_REGISTRY 行为验证"""

    def test_registry_get_chunker(self):
        """注册表: source_type 映射正确"""
        chunker = get_chunker("mac_notes")
        assert isinstance(chunker, CompositeChunker)
        default = get_chunker("default")
        assert isinstance(default, RecursiveCharacterChunker)

    def test_registry_default(self):
        """注册表: 未知类型返回兜底策略"""
        chunker = get_chunker("unknown_type_xyz")
        assert isinstance(chunker, RecursiveCharacterChunker)
        chunker2 = get_chunker("non_existent")
        assert isinstance(chunker2, RecursiveCharacterChunker)
