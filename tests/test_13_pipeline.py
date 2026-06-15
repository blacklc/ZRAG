"""切片 12 — IngestionPipeline 测试

测试内容:
  - 基本流程: Source 产出文档, 完整处理
  - 增量模式: processed_docs hash 相同则跳过
  - 全量模式: full=True 忽略缓存
  - 错误处理: 单篇失败不影响后续文档
  - 文档完成回调与取消中断回调
  - 错误回调
  - 各组件调用验证
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from zrag.embed.base import EmbeddingModel
from zrag.ingest.chunking.base import ChunkingStrategy
from zrag.ingest.pipeline import (
    ErrorEvent,
    IngestReport,
    IngestionPipeline,
)
from zrag.ingest.sources.base import DocumentSource
from zrag.models.document import Chunk, RawDocument


def _make_doc(source_id: str, content: str, title: str = "Test Doc") -> RawDocument:
    """创建 RawDocument 测试辅助方法

    @param source_id: 文档标识
    @type  source_id: str
    @param content: 文档内容
    @type  content: str
    @param title: 文档标题, defaults to "Test Doc"
    @type  title: str, optional

    @return: RawDocument 实例
    @type:   RawDocument
    """
    return RawDocument(
        source_id=source_id,
        source_type="test",
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        metadata={"title": title},
    )


def _make_chunk(source_id: str, index: int, content: str) -> Chunk:
    """创建 Chunk 测试辅助方法

    @param source_id: 文档标识
    @type  source_id: str
    @param index: 分块序号
    @type  index: int
    @param content: 分块内容
    @type  content: str

    @return: Chunk 实例
    @type:   Chunk
    """
    return Chunk(
        chunk_id=f"{source_id}_chunk_{index}",
        source_id=source_id,
        source_type="test",
        doc_title="Test Doc",
        content=content,
        chunk_index=index,
    )


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_source():
    """返回 mock DocumentSource"""
    source = MagicMock(spec=DocumentSource)
    return source


@pytest.fixture
def mock_chunker():
    """返回 mock ChunkingStrategy"""
    chunker = MagicMock(spec=ChunkingStrategy)
    return chunker


@pytest.fixture
def mock_embedder():
    """返回 mock EmbeddingModel"""
    embedder = MagicMock(spec=EmbeddingModel)
    return embedder


@pytest.fixture
def mock_sqlite():
    """返回 mock SQLiteStore"""
    sqlite = MagicMock()
    sqlite.get_processed.return_value = None
    return sqlite


@pytest.fixture
def mock_chroma():
    """返回 mock ChromaStore"""
    chroma = MagicMock()
    return chroma


@pytest.fixture
def pipeline(mock_sqlite, mock_chroma, mock_embedder, mock_chunker):
    """返回注入 mock 依赖的 IngestionPipeline 实例"""
    return IngestionPipeline(
        sqlite_store=mock_sqlite,
        chroma_store=mock_chroma,
        embedder=mock_embedder,
        chunker=mock_chunker,
        batch_size=10,
    )


# ============================================================
# Tests
# ============================================================


class TestIngestionPipeline:
    """IngestionPipeline 行为验证"""

    # --------------------------------------------------
    # 1. 基本流程
    # --------------------------------------------------

    def test_run_processes_documents(self, pipeline, mock_source, mock_chunker, mock_embedder):
        """基本流程: Source 产出 2 篇文档, 报告 total=2"""
        doc1 = _make_doc("doc_1", "内容一")
        doc2 = _make_doc("doc_2", "内容二")
        mock_source.fetch_batch.return_value = iter([[doc1, doc2]])

        chunk1 = _make_chunk("doc_1", 0, "内容一")
        chunk2 = _make_chunk("doc_2", 0, "内容二")
        mock_chunker.chunk.side_effect = [[chunk1], [chunk2]]
        mock_embedder.embed.side_effect = [[[0.1, 0.2]], [[0.3, 0.4]]]

        report = pipeline.run(source=mock_source)

        assert report.total == 2
        assert report.new == 2
        assert report.updated == 0
        assert report.skipped == 0
        assert report.failed == 0

    # --------------------------------------------------
    # 2. 增量跳过
    # --------------------------------------------------

    def test_skip_unchanged(self, pipeline, mock_source, mock_sqlite, mock_chunker, mock_embedder):
        """增量模式: processed_docs 中 hash 相同 -> 跳过"""
        doc1 = _make_doc("doc_1", "内容一")
        doc2 = _make_doc("doc_2", "内容二")
        mock_source.fetch_batch.return_value = iter([[doc1, doc2]])

        # doc1 hash 匹配 -> 跳过
        mock_sqlite.get_processed.side_effect = [
            {"source_id": "doc_1", "content_hash": doc1.content_hash},
            {"source_id": "doc_2", "content_hash": doc2.content_hash},
        ]

        report = pipeline.run(source=mock_source)

        assert report.total == 2
        assert report.skipped == 2
        assert report.new == 0
        assert report.updated == 0
        assert report.failed == 0
        # chunker 和 embedder 不应被调用
        mock_chunker.chunk.assert_not_called()
        mock_embedder.embed.assert_not_called()

    # --------------------------------------------------
    # 3. 全量导入
    # --------------------------------------------------

    def test_full_ignores_cache(self, pipeline, mock_source, mock_sqlite, mock_chunker, mock_embedder):
        """全量模式: full=True 忽略 processed_docs"""
        doc1 = _make_doc("doc_1", "内容一")
        mock_source.fetch_batch.return_value = iter([[doc1]])

        # 即使 processed_docs 存在且 hash 相同, 全量模式下也重新处理
        mock_sqlite.get_processed.return_value = {
            "source_id": "doc_1",
            "content_hash": doc1.content_hash,
        }

        mock_chunker.chunk.return_value = [_make_chunk("doc_1", 0, "内容一")]
        mock_embedder.embed.return_value = [[0.1, 0.2]]

        report = pipeline.run(source=mock_source, full=True)

        assert report.total == 1
        assert report.new == 1
        assert report.skipped == 0
        assert report.updated == 0
        assert report.failed == 0
        # full=True 时不应查询 processed_docs
        assert mock_sqlite.get_processed.call_count == 0

    # --------------------------------------------------
    # 4. 单篇失败继续
    # --------------------------------------------------

    def test_error_continues(self, pipeline, mock_source, mock_chunker, mock_embedder):
        """单篇失败不影响后续文档"""
        doc1 = _make_doc("doc_1", "内容一")
        doc2 = _make_doc("doc_2", "内容二")
        mock_source.fetch_batch.return_value = iter([[doc1, doc2]])

        chunk2 = _make_chunk("doc_2", 0, "内容二")
        # doc1 抛异常, doc2 正常
        mock_chunker.chunk.side_effect = [ValueError("处理 doc1 失败"), [chunk2]]
        mock_embedder.embed.return_value = [[0.3, 0.4]]

        report = pipeline.run(source=mock_source)

        assert report.total == 2
        assert report.failed == 1
        assert report.new == 1
        assert len(report.errors) == 1
        assert report.errors[0].source_id == "doc_1"
        assert "处理 doc1 失败" in report.errors[0].error

    # --------------------------------------------------
    # 5. on_document_done 回调
    # --------------------------------------------------

    def test_on_document_done_called(self, pipeline, mock_source, mock_chunker, mock_embedder):
        """on_document_done 在每篇文档处理后调用"""
        doc1 = _make_doc("doc_1", "内容一")
        doc2 = _make_doc("doc_2", "内容二")
        mock_source.fetch_batch.return_value = iter([[doc1, doc2]])

        mock_chunker.chunk.side_effect = [
            [_make_chunk("doc_1", 0, "块一")],
            [_make_chunk("doc_2", 0, "块二")],
        ]
        mock_embedder.embed.return_value = [[0.1], [0.2]]

        calls = []
        pipeline.run(source=mock_source, on_document_done=lambda: calls.append(1))

        assert len(calls) == 2

    def test_on_document_done_on_failure(self, pipeline, mock_source, mock_chunker, mock_embedder):
        """即使文档处理失败，on_document_done 也会被调用"""
        doc1 = _make_doc("doc_1", "内容一")
        doc2 = _make_doc("doc_2", "内容二")
        mock_source.fetch_batch.return_value = iter([[doc1, doc2]])

        mock_chunker.chunk.side_effect = [ValueError("失败"), [_make_chunk("doc_2", 0, "块二")]]
        mock_embedder.embed.return_value = [[0.3]]

        calls = []
        pipeline.run(source=mock_source, on_document_done=lambda: calls.append(1))

        assert len(calls) == 2  # 成功和失败都调用

    def test_should_cancel_interrupts(self, pipeline, mock_source, mock_chunker, mock_embedder):
        """should_cancel 返回 True 时中断后续处理"""
        doc1 = _make_doc("doc_1", "内容一")
        doc2 = _make_doc("doc_2", "内容二")
        doc3 = _make_doc("doc_3", "内容三")
        mock_source.fetch_batch.return_value = iter([[doc1, doc2, doc3]])

        mock_chunker.chunk.side_effect = [
            [_make_chunk("doc_1", 0, "块一")],
            [_make_chunk("doc_2", 0, "块二")],
        ]
        mock_embedder.embed.return_value = [[0.1], [0.2]]

        cancel_after = 0

        def should_cancel():
            nonlocal cancel_after
            cancel_after += 1
            return cancel_after > 1  # 第2篇文档后取消

        report = pipeline.run(source=mock_source, should_cancel=should_cancel)

        assert report.total == 3
        # 第1篇处理了，第2篇开始前取消
        assert report.new + report.skipped <= 2

    # --------------------------------------------------
    # 6. 错误回调
    # --------------------------------------------------

    def test_on_error_called(self, mock_sqlite, mock_chroma, mock_embedder, mock_chunker):
        """错误回调被调用"""
        doc1 = _make_doc("doc_1", "内容一")
        mock_source = MagicMock(spec=DocumentSource)
        mock_source.fetch_batch.return_value = iter([[doc1]])

        mock_chunker.chunk.side_effect = ValueError("出错了")

        errors = []
        pipeline = IngestionPipeline(
            sqlite_store=mock_sqlite,
            chroma_store=mock_chroma,
            embedder=mock_embedder,
            chunker=mock_chunker,
            on_error=errors.append,
        )

        report = pipeline.run(source=mock_source)

        assert report.failed == 1
        assert len(errors) == 1
        assert errors[0].source_id == "doc_1"
        assert "出错了" in errors[0].error

    # --------------------------------------------------
    # 7. chunker 调用验证
    # --------------------------------------------------

    def test_chunking_called(self, pipeline, mock_source, mock_chunker, mock_embedder):
        """chunker 被正确调用"""
        doc1 = _make_doc("doc_1", "内容一")
        doc2 = _make_doc("doc_2", "内容二")
        mock_source.fetch_batch.return_value = iter([[doc1, doc2]])

        chunk1 = _make_chunk("doc_1", 0, "内容一_块")
        chunk2 = _make_chunk("doc_2", 0, "内容二_块")
        mock_chunker.chunk.side_effect = [[chunk1], [chunk2]]
        mock_embedder.embed.return_value = [[0.1], [0.2]]

        pipeline.run(source=mock_source)

        assert mock_chunker.chunk.call_count == 2
        # 验证传入的是 RawDocument
        first_call_arg = mock_chunker.chunk.call_args_list[0][0][0]
        assert isinstance(first_call_arg, RawDocument)
        assert first_call_arg.source_id == "doc_1"

    # --------------------------------------------------
    # 8. embedder 调用验证
    # --------------------------------------------------

    def test_embedding_called(self, pipeline, mock_source, mock_chunker, mock_embedder):
        """embedder 被正确调用"""
        doc1 = _make_doc("doc_1", "内容一")
        mock_source.fetch_batch.return_value = iter([[doc1]])

        chunk1 = _make_chunk("doc_1", 0, "内容一_块")
        mock_chunker.chunk.return_value = [chunk1]
        mock_embedder.embed.return_value = [[0.1]]

        pipeline.run(source=mock_source)

        mock_embedder.embed.assert_called_once_with(["内容一_块"])

    # --------------------------------------------------
    # 9. SQLite + ChromaDB 写入验证
    # --------------------------------------------------

    def test_sqlite_and_chroma_written(self, pipeline, mock_source, mock_sqlite, mock_chroma, mock_chunker, mock_embedder):
        """SQLite + ChromaDB 写入被调用"""
        doc1 = _make_doc("doc_1", "内容一")
        mock_source.fetch_batch.return_value = iter([[doc1]])

        chunk1 = _make_chunk("doc_1", 0, "内容一_块")
        mock_chunker.chunk.return_value = [chunk1]
        mock_embedder.embed.return_value = [[0.1, 0.2]]

        pipeline.run(source=mock_source)

        # SQLite 事务: delete + add_chunks + upsert_processed
        mock_sqlite.transaction.assert_called_once()
        mock_sqlite.delete_by_source.assert_called_once_with("doc_1")
        mock_sqlite.add_chunks.assert_called_once_with([chunk1])
        mock_sqlite.upsert_processed.assert_called_once_with(doc1)

        # ChromaDB: delete + add
        mock_chroma.delete_by_source.assert_called_once_with("doc_1")
        mock_chroma.add.assert_called_once()
        add_kwargs = mock_chroma.add.call_args[1]
        assert add_kwargs["ids"] == ["doc_1_chunk_0"]
        assert add_kwargs["embeddings"] == [[0.1, 0.2]]
