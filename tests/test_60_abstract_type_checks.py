"""测试切片 60 — 抽象类父类型检查机制

根据《代码样式指南》中的"抽象类的父类型检查机制"要求:
- 如果一个功能逻辑内使用了抽象类来实现功能扩展的需求，
  则该功能逻辑中必须在使用实体类之前检查该实体类是否继承了指定的抽象类。
- 如果没有通过检查机制，则应该向上抛出异常并终止后续流程。

测试以下 5 个检查点:
1. IngestionPipeline.__init__ embedder 必须是 EmbeddingModel 的子类
2. IngestionPipeline.__init__ chunker 必须是 ChunkingStrategy 的子类
3. IngestionPipeline.run() source 必须是 DocumentSource 的子类
4. Retriever.__init__ embedder 必须是 EmbeddingModel 的子类
5. ConversationViewSet._check_llm_provider 必须是 LLMProvider 的子类
"""

from unittest.mock import MagicMock, patch

import pytest

from zrag.embed.base import EmbeddingModel
from zrag.ingest.chunking.base import ChunkingStrategy
from zrag.ingest.pipeline import IngestionPipeline
from zrag.ingest.sources.base import DocumentSource
from zrag.llm.base import LLMProvider
from zrag.retrieval.retriever import Retriever

from dataclasses import fields
from zrag.models.retrieval import SearchResult


# ---- 最小子类实现 ----

class _MinimalEmbedder(EmbeddingModel):
    """EmbeddingModel 的最小子类实现，仅用于测试类型检查通过场景"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 4 for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [0.0] * 4

    @property
    def dimension(self) -> int:
        return 4


class _MinimalChunker(ChunkingStrategy):
    """ChunkingStrategy 的最小子类实现"""

    def chunk(self, document):
        from zrag.models.document import Chunk
        return [Chunk(
            chunk_id="test",
            source_id="test",
            source_type="test",
            doc_title="test",
            content="test",
            chunk_index=0,
        )]


class _MinimalSource(DocumentSource):
    """DocumentSource 的最小子类实现"""

    @property
    def source_type(self) -> str:
        return "test_source"

    def fetch_batch(self, batch_size: int = 10):
        yield []


class _MinimalLLMProvider(LLMProvider):
    """LLMProvider 的最小子类实现"""

    def chat(self, messages: list[dict]) -> str | None:
        return "test response"

    @property
    def model(self) -> str:
        return "test-model"

    @property
    def timeout(self) -> float:
        return 30.0


# -----------------------------------------------------------
# 1. IngestionPipeline.__init__ — embedder 检查
# -----------------------------------------------------------

class TestIngestionPipelineEmbedderCheck:
    """IngestionPipeline 构造时对 embedder 的类型检查"""

    def test_embedder_valid_subclass(self):
        """传入 EmbeddingModel 子类时正常通过"""
        pipeline = IngestionPipeline(
            sqlite_store=MagicMock(),
            chroma_store=MagicMock(),
            embedder=_MinimalEmbedder(),
            chunker=_MinimalChunker(),
        )
        assert pipeline.embedder is not None

    def test_embedder_not_subclass_raises_typeerror(self):
        """传入 object() 作为 embedder 时抛出 TypeError"""
        with pytest.raises(TypeError) as exc_info:
            IngestionPipeline(
                sqlite_store=MagicMock(),
                chroma_store=MagicMock(),
                embedder=object(),
                chunker=_MinimalChunker(),
            )
        assert "必须是 EmbeddingModel 的子类" in str(exc_info.value)

    def test_embedder_error_message_contains_actual_type(self):
        """TypeError 消息中包含实际类型名"""
        with pytest.raises(TypeError) as exc_info:
            IngestionPipeline(
                sqlite_store=MagicMock(),
                chroma_store=MagicMock(),
                embedder=42,
                chunker=_MinimalChunker(),
            )
        assert "int" in str(exc_info.value)


# -----------------------------------------------------------
# 2. IngestionPipeline.__init__ — chunker 检查
# -----------------------------------------------------------

class TestIngestionPipelineChunkerCheck:
    """IngestionPipeline 构造时对 chunker 的类型检查"""

    def test_chunker_valid_subclass(self):
        """传入 ChunkingStrategy 子类时正常通过"""
        pipeline = IngestionPipeline(
            sqlite_store=MagicMock(),
            chroma_store=MagicMock(),
            embedder=_MinimalEmbedder(),
            chunker=_MinimalChunker(),
        )
        assert pipeline.chunker is not None

    def test_chunker_not_subclass_raises_typeerror(self):
        """传入 object() 作为 chunker 时抛出 TypeError"""
        with pytest.raises(TypeError) as exc_info:
            IngestionPipeline(
                sqlite_store=MagicMock(),
                chroma_store=MagicMock(),
                embedder=_MinimalEmbedder(),
                chunker=object(),
            )
        assert "必须是 ChunkingStrategy 的子类" in str(exc_info.value)


# -----------------------------------------------------------
# 3. IngestionPipeline.run() — source 检查
# -----------------------------------------------------------

class TestIngestionPipelineSourceCheck:
    """IngestionPipeline.run() 对 source 的类型检查"""

    def test_source_valid_subclass(self):
        """传入 DocumentSource 子类时正常执行"""
        pipeline = IngestionPipeline(
            sqlite_store=MagicMock(),
            chroma_store=MagicMock(),
            embedder=_MinimalEmbedder(),
            chunker=_MinimalChunker(),
        )
        report = pipeline.run(source=_MinimalSource())
        assert report is not None

    def test_source_not_subclass_raises_typeerror(self):
        """传入 object() 作为 source 时抛出 TypeError"""
        pipeline = IngestionPipeline(
            sqlite_store=MagicMock(),
            chroma_store=MagicMock(),
            embedder=_MinimalEmbedder(),
            chunker=_MinimalChunker(),
        )
        with pytest.raises(TypeError) as exc_info:
            pipeline.run(source=object())
        assert "必须是 DocumentSource 的子类" in str(exc_info.value)

    def test_source_error_message_contains_actual_type(self):
        """TypeError 消息中包含实际类型名"""
        pipeline = IngestionPipeline(
            sqlite_store=MagicMock(),
            chroma_store=MagicMock(),
            embedder=_MinimalEmbedder(),
            chunker=_MinimalChunker(),
        )
        with pytest.raises(TypeError) as exc_info:
            pipeline.run(source="not_a_source")
        assert "str" in str(exc_info.value)


# -----------------------------------------------------------
# 4. Retriever.__init__ — embedder 检查
# -----------------------------------------------------------

class TestRetrieverEmbedderCheck:
    """Retriever 构造时对 embedder 的类型检查"""

    def test_embedder_valid_subclass(self):
        """传入 EmbeddingModel 子类时正常通过"""
        retriever = Retriever(
            sqlite_store=MagicMock(),
            chroma_store=MagicMock(),
            embedder=_MinimalEmbedder(),
        )
        assert retriever.embedder is not None

    def test_embedder_not_subclass_raises_typeerror(self):
        """传入 object() 作为 embedder 时抛出 TypeError"""
        with pytest.raises(TypeError) as exc_info:
            Retriever(
                sqlite_store=MagicMock(),
                chroma_store=MagicMock(),
                embedder=object(),
            )
        assert "必须是 EmbeddingModel 的子类" in str(exc_info.value)

    def test_embedder_error_message_contains_actual_type(self):
        """TypeError 消息中包含实际类型名"""
        with pytest.raises(TypeError) as exc_info:
            Retriever(
                sqlite_store=MagicMock(),
                chroma_store=MagicMock(),
                embedder=3.14,
            )
        assert "float" in str(exc_info.value)


# -----------------------------------------------------------
# 5. ConversationViewSet._check_llm_provider — LLMProvider 检查
# -----------------------------------------------------------

class TestCheckLLMProvider:
    """ConversationViewSet._check_llm_provider 对 LLMProvider 的类型检查"""

    def test_llm_provider_valid_subclass(self):
        """传入 LLMProvider 子类时正常通过"""
        from zrag.api.views import ConversationViewSet
        # 应为静默通过（不抛出异常）
        ConversationViewSet._check_llm_provider(_MinimalLLMProvider())

    def test_llm_provider_not_subclass_raises_typeerror(self):
        """传入 object() 时抛出 TypeError"""
        from zrag.api.views import ConversationViewSet
        with pytest.raises(TypeError) as exc_info:
            ConversationViewSet._check_llm_provider(object())
        assert "必须是 LLMProvider 的子类" in str(exc_info.value)

    def test_llm_provider_error_message_contains_actual_type(self):
        """TypeError 消息中包含实际类型名"""
        from zrag.api.views import ConversationViewSet
        with pytest.raises(TypeError) as exc_info:
            ConversationViewSet._check_llm_provider(None)
        assert "NoneType" in str(exc_info.value)

    def test_mock_that_is_not_subclass_raises_typeerror(self):
        """MagicMock（未指定 spec）不是 LLMProvider 的子类，应抛出 TypeError"""
        from zrag.api.views import ConversationViewSet
        with pytest.raises(TypeError) as exc_info:
            ConversationViewSet._check_llm_provider(MagicMock())
        # MagicMock 的类型名是 "MagicMock"，不是 LLMProvider 的子类
        assert "MagicMock" in str(exc_info.value)

    def test_minimal_provider_spec_mock_passes(self):
        """使用 spec=_MinimalLLMProvider 的 MagicMock 可通过检查

        注意：MagicMock(spec=LLMProvider) 不会成为 LLMProvider 的子类，
        isinstance 检查要求实际继承。这里使用真正的子类实例来验证通过场景。
        """
        from zrag.api.views import ConversationViewSet
        provider = _MinimalLLMProvider()
        # 应为静默通过
        ConversationViewSet._check_llm_provider(provider)


# -----------------------------------------------------------
# 6. SearchResult — chunk_index 字段
# -----------------------------------------------------------

class TestSearchResultChunkIndex:
    """SearchResult 新增 chunk_index 字段"""

    def test_chunk_index_field_exists(self):
        """SearchResult 应包含 chunk_index 字段"""
        field_names = {f.name for f in fields(SearchResult)}
        assert "chunk_index" in field_names

    def test_chunk_index_default_none(self):
        """chunk_index 默认值应为 None"""
        result = SearchResult(
            chunk_id="c1",
            content="test",
            doc_title="doc",
            source_id="s1",
            source_type="type1",
            score=0.95,
        )
        assert result.chunk_index is None

    def test_chunk_index_accepts_int(self):
        """chunk_index 可以传入整数"""
        result = SearchResult(
            chunk_id="c1",
            content="test",
            doc_title="doc",
            source_id="s1",
            source_type="type1",
            score=0.95,
            chunk_index=3,
        )
        assert result.chunk_index == 3
