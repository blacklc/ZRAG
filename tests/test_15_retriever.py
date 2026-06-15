"""切片 15: Retriever（混合检索 + RRF）测试

测试 Retriever 的 hybrid_search 方法, 包括:
- 基本检索流程
- RRF 融合去重逻辑
- RRF 分数计算正确性
- 边界条件: 向量检索无结果 / 两者均无结果
"""

from unittest.mock import MagicMock, patch

import pytest

from zrag.embed.base import EmbeddingModel
from zrag.models.retrieval import SearchResult
from zrag.retrieval.retriever import Retriever


class TestRetriever:
    """Retriever 单元测试"""

    # ---- 辅助方法 ----

    def _make_mocks(self):
        """创建 Mock 的 SQLiteStore / ChromaStore / Embedder

        @return: (sqlite_store, chroma_store, embedder) 三元组
        @type:   tuple[MagicMock, MagicMock, MagicMock]
        """
        sqlite_store = MagicMock()
        chroma_store = MagicMock()
        embedder = MagicMock(spec=EmbeddingModel)
        embedder.embed_query.return_value = [0.1, 0.2, 0.3]
        return sqlite_store, chroma_store, embedder

    def _make_retriever(self, sqlite_store, chroma_store, embedder) -> Retriever:
        """构造 Retriever 实例

        @param sqlite_store: Mock SQLiteStore
        @type  sqlite_store: MagicMock
        @param chroma_store: Mock ChromaStore
        @type  chroma_store: MagicMock
        @param embedder: Mock Embedder
        @type  embedder: MagicMock

        @return: Retriever 实例
        @type:   Retriever
        """
        return Retriever(
            sqlite_store=sqlite_store,
            chroma_store=chroma_store,
            embedder=embedder,
        )

    # ---- 测试用例 ----

    def test_hybrid_search_returns_results(self):
        """基本流程: 向量检索和关键词检索都有结果, 返回 top-k SearchResult 列表"""
        sqlite_store, chroma_store, embedder = self._make_mocks()

        # 模拟 embedder.embed_query 返回值
        embedder.embed_query.return_value = [0.1, 0.2, 0.3]

        # 模拟 ChromaStore 向量检索结果（按 distance 升序排列）
        chroma_store.similarity_search.return_value = [
            {'id': 'chunk_1', 'metadata': {'doc_title': 'Doc1', 'source_id': 'src_1',
                                            'source_type': 'txt'}, 'distance': 0.1},
            {'id': 'chunk_2', 'metadata': {'doc_title': 'Doc2', 'source_id': 'src_2',
                                            'source_type': 'txt'}, 'distance': 0.2},
            {'id': 'chunk_3', 'metadata': {'doc_title': 'Doc3', 'source_id': 'src_3',
                                            'source_type': 'txt'}, 'distance': 0.3},
        ]

        # 模拟 SQLiteStore FTS5 检索结果（按 bm25_score 升序排列）
        sqlite_store.search_fts5.return_value = [
            {'chunk_id': 'chunk_1', 'content': 'Content 1', 'doc_title': 'Doc1',
             'source_id': 'src_1', 'source_type': 'txt', 'bm25_score': -5.0},
            {'chunk_id': 'chunk_2', 'content': 'Content 2', 'doc_title': 'Doc2',
             'source_id': 'src_2', 'source_type': 'txt', 'bm25_score': -4.0},
            {'chunk_id': 'chunk_4', 'content': 'Content 4', 'doc_title': 'Doc4',
             'source_id': 'src_4', 'source_type': 'txt', 'bm25_score': -3.0},
        ]

        retriever = self._make_retriever(sqlite_store, chroma_store, embedder)
        results = retriever.hybrid_search('test query', k=3)

        # 验证
        assert len(results) == 3
        assert isinstance(results[0], SearchResult)

        # chunk_1 在两种检索中都是第 1 名, 应该 RRF 分数最高
        assert results[0].chunk_id == 'chunk_1'
        # chunk_2 在两种检索中都是第 2 名
        assert results[1].chunk_id == 'chunk_2'

        # chunk_3 仅在向量检索中出现（第 3 名）
        # chunk_4 仅在关键词检索中出现（第 3 名）
        # 验证 chunk_3 的 content 为空字符串（通过 metadata 兜底）
        # 验证 chunk_4 的 content 来自 keyword_results
        chunk_ids = {r.chunk_id for r in results}
        assert 'chunk_3' in chunk_ids or 'chunk_4' in chunk_ids

        # 验证 embedder 被调用
        embedder.embed_query.assert_called_once_with('test query')
        chroma_store.similarity_search.assert_called_once()
        sqlite_store.search_fts5.assert_called_once_with('test query', 6)

    def test_rrf_deduplicates(self):
        """RRF 融合去重: 同一 chunk_id 同时出现在两种检索结果中时, 只返回一条结果"""
        sqlite_store, chroma_store, embedder = self._make_mocks()

        chroma_store.similarity_search.return_value = [
            {'id': 'chunk_A', 'metadata': {'doc_title': 'DocA', 'source_id': 'src_A',
                                            'source_type': 'txt'}, 'distance': 0.1},
            {'id': 'chunk_B', 'metadata': {'doc_title': 'DocB', 'source_id': 'src_B',
                                            'source_type': 'txt'}, 'distance': 0.2},
        ]

        sqlite_store.search_fts5.return_value = [
            {'chunk_id': 'chunk_A', 'content': 'Content A', 'doc_title': 'DocA',
             'source_id': 'src_A', 'source_type': 'txt', 'bm25_score': -5.0},
            {'chunk_id': 'chunk_C', 'content': 'Content C', 'doc_title': 'DocC',
             'source_id': 'src_C', 'source_type': 'txt', 'bm25_score': -4.0},
        ]

        retriever = self._make_retriever(sqlite_store, chroma_store, embedder)
        results = retriever.hybrid_search('test query', k=10)

        # chunk_A 应在结果中只出现一次
        chunk_ids = [r.chunk_id for r in results]
        assert chunk_ids.count('chunk_A') == 1
        # 总共 3 个不同的 chunk_id: chunk_A, chunk_B, chunk_C
        assert len(results) == 3

    def test_rrf_scoring(self):
        """验证 RRF 分数计算正确性

        RRF: score(d) = 1/(60 + rank_vector) + 1/(60 + rank_bm25)
        chunk_1: vector rank=1, keyword rank=1
                 score = 1/(60+1) + 1/(60+1) = 1/61 + 1/61 = 2/61 ≈ 0.03279
        chunk_2: vector rank=2, keyword rank=2
                 score = 1/(60+2) + 1/(60+2) = 1/62 + 1/62 = 2/62 ≈ 0.03226
        chunk_3: vector rank=3, keyword rank=inf
                 score = 1/(60+3) + 0 = 1/63 ≈ 0.01587
        chunk_4: vector rank=inf, keyword rank=3
                 score = 0 + 1/(60+3) = 1/63 ≈ 0.01587
        """
        sqlite_store, chroma_store, embedder = self._make_mocks()

        chroma_store.similarity_search.return_value = [
            {'id': 'chunk_1', 'metadata': {}, 'distance': 0.1},
            {'id': 'chunk_2', 'metadata': {}, 'distance': 0.2},
            {'id': 'chunk_3', 'metadata': {'doc_title': 'Doc3', 'source_id': 'src_3',
                                            'source_type': 'txt'}, 'distance': 0.3},
        ]

        sqlite_store.search_fts5.return_value = [
            {'chunk_id': 'chunk_1', 'content': 'C1', 'doc_title': 'D1',
             'source_id': 'S1', 'source_type': 'txt', 'bm25_score': -5.0},
            {'chunk_id': 'chunk_2', 'content': 'C2', 'doc_title': 'D2',
             'source_id': 'S2', 'source_type': 'txt', 'bm25_score': -4.0},
            {'chunk_id': 'chunk_4', 'content': 'C4', 'doc_title': 'D4',
             'source_id': 'S4', 'source_type': 'txt', 'bm25_score': -3.0},
        ]

        # 对于 chunk_3（只在向量检索中）, 模拟 SQLite 中有对应记录
        sqlite_store.fetch_one.return_value = {
            'content': '',
            'doc_title': 'Doc3',
            'source_id': 'src_3',
            'source_type': 'txt',
        }

        retriever = self._make_retriever(sqlite_store, chroma_store, embedder)
        results = retriever.hybrid_search('test', k=10)

        result_map = {r.chunk_id: r for r in results}

        # chunk_1: score = 2/61
        assert result_map['chunk_1'].score == pytest.approx(2.0 / 61.0, rel=1e-5)
        # chunk_2: score = 2/62
        assert result_map['chunk_2'].score == pytest.approx(2.0 / 62.0, rel=1e-5)
        # chunk_3: score = 1/63
        assert result_map['chunk_3'].score == pytest.approx(1.0 / 63.0, rel=1e-5)
        # chunk_4: score = 1/63
        assert result_map['chunk_4'].score == pytest.approx(1.0 / 63.0, rel=1e-5)

        # 验证排序: chunk_1 > chunk_2 > chunk_3 == chunk_4
        assert results[0].chunk_id == 'chunk_1'
        assert results[1].chunk_id == 'chunk_2'
        # chunk_3 和 chunk_4 分数相同, 顺序不确定, 但都排在最后
        assert results[2].chunk_id in ('chunk_3', 'chunk_4')
        assert results[3].chunk_id in ('chunk_3', 'chunk_4')
        assert results[2].chunk_id != results[3].chunk_id

    def test_empty_vector_results(self):
        """向量检索无结果但 FTS5 有结果: 应正确返回关键词检索结果"""
        sqlite_store, chroma_store, embedder = self._make_mocks()

        # 向量检索返回空
        chroma_store.similarity_search.return_value = []

        sqlite_store.search_fts5.return_value = [
            {'chunk_id': 'chunk_1', 'content': 'Content 1', 'doc_title': 'Doc1',
             'source_id': 'src_1', 'source_type': 'txt', 'bm25_score': -5.0},
        ]

        retriever = self._make_retriever(sqlite_store, chroma_store, embedder)
        results = retriever.hybrid_search('test query', k=10)

        assert len(results) == 1
        assert results[0].chunk_id == 'chunk_1'
        assert results[0].content == 'Content 1'
        assert results[0].score == pytest.approx(1.0 / 61.0, rel=1e-5)

    def test_empty_all(self):
        """向量检索和关键词检索均无结果: 应返回空列表"""
        sqlite_store, chroma_store, embedder = self._make_mocks()

        chroma_store.similarity_search.return_value = []
        sqlite_store.search_fts5.return_value = []

        retriever = self._make_retriever(sqlite_store, chroma_store, embedder)
        results = retriever.hybrid_search('test query', k=10)

        assert len(results) == 0
        assert results == []


class TestBuildResultsChunkIndex:
    def test_chunk_index_in_search_result(self):
        """验证 SearchResult 包含 chunk_index 字段"""
        from zrag.models.retrieval import SearchResult
        sr = SearchResult(
            chunk_id="test", content="test", doc_title="test",
            source_id="test", source_type="test", score=1.0,
            chunk_index=5
        )
        assert sr.chunk_index == 5
