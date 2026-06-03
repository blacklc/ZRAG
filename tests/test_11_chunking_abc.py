"""切片 10 — ChunkingStrategy ABC 测试

测试 ChunkingStrategy 抽象基类的行为约束：
  - 不能直接实例化
  - 未实现抽象方法的子类不能实例化
  - 正确实现的子类可正常使用
  - chunk() 返回 list[Chunk]
  - Chunk 的 source_id / source_type / doc_title 与 RawDocument 一致
  - Chunk 的 chunk_index 从 0 开始递增
"""

import pytest

from zrag.models.document import RawDocument, Chunk
from zrag.ingest.chunking.base import ChunkingStrategy


class FakeChunker(ChunkingStrategy):
    """测试用的 FakeChunker — 实现了 chunk() 抽象方法"""

    def __init__(self, max_size=100):
        self.max_size = max_size

    def chunk(self, document: RawDocument) -> list[Chunk]:
        """将文档按固定大小切块

        @param document: 待分块的原始文档
        @type  document: RawDocument

        @return: 分块后的 Chunk 列表
        @type:   list[Chunk]
        """
        chunks = []
        content = document.content
        for i in range(0, len(content), self.max_size):
            segment = content[i:i + self.max_size]
            chunks.append(Chunk(
                chunk_id=f"{document.source_id}_chunk_{i // self.max_size}",
                source_id=document.source_id,
                source_type=document.source_type,
                doc_title=document.metadata.get("title", "") if document.metadata else "",
                content=segment,
                chunk_index=i // self.max_size,
            ))
        return chunks


class BadChunker(ChunkingStrategy):
    """测试用的 BadChunker — 未实现 chunk() 抽象方法"""
    pass


class TestChunkingStrategyABC:
    """ChunkingStrategy ABC 行为验证"""

    def test_cannot_instantiate_abc(self):
        """ChunkingStrategy 是 ABC, 不能直接实例化"""
        with pytest.raises(TypeError):
            ChunkingStrategy()

    def test_concrete_strategy_works(self):
        """实现 chunk() 的子类可正常使用"""
        chunker = FakeChunker(max_size=50)
        assert isinstance(chunker, ChunkingStrategy)
        assert chunker.max_size == 50

    def test_missing_method_raises(self):
        """未实现抽象方法的子类实例化时抛出 TypeError"""
        with pytest.raises(TypeError):
            BadChunker()

    def test_chunk_returns_chunk_list(self):
        """chunk() 返回 list[Chunk]"""
        chunker = FakeChunker(max_size=50)
        doc = RawDocument(
            source_id="test_doc_001",
            source_type="local_file",
            content="Hello world. This is a test document for chunking.",
            content_hash="abc123",
            metadata={"title": "Test Doc"},
        )
        result = chunker.chunk(doc)
        assert isinstance(result, list)
        assert all(isinstance(c, Chunk) for c in result)

    def test_chunk_preserves_source_info(self):
        """Chunk 的 source_id / source_type / doc_title 与 RawDocument 一致"""
        chunker = FakeChunker(max_size=100)
        doc = RawDocument(
            source_id="doc_002",
            source_type="mac_notes",
            content="Short content.",
            content_hash="def456",
            metadata={"title": "My Note"},
        )
        chunks = chunker.chunk(doc)
        for c in chunks:
            assert c.source_id == doc.source_id
            assert c.source_type == doc.source_type
            assert c.doc_title == doc.metadata["title"]

    def test_chunk_indexing(self):
        """Chunk 的 chunk_index 从 0 开始递增"""
        chunker = FakeChunker(max_size=30)
        doc = RawDocument(
            source_id="doc_003",
            source_type="local_file",
            content="A" * 120,
            content_hash="ghi789",
        )
        chunks = chunker.chunk(doc)
        for i, c in enumerate(chunks):
            assert c.chunk_index == i
