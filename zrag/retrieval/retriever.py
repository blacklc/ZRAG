"""混合检索器模块

提供融合向量检索（ChromaDB）与关键词检索（SQLite FTS5）的混合检索器,
使用 RRF（Reciprocal Rank Fusion）算法对两种检索结果进行融合与重排序。
"""

import logging

from zrag.embed.base import EmbeddingModel
from zrag.models.retrieval import SearchResult
from zrag.retrieval.query_rewriter import QueryRewriter
from zrag.store.sqlite_store import SQLiteStore
from zrag.store.vector_store import ChromaStore

logger = logging.getLogger(__name__)


class Retriever:
    """混合检索器

    融合向量检索（ChromaDB）与关键词检索（SQLite FTS5）的结果,
    使用 RRF（Reciprocal Rank Fusion）算法进行结果融合与重排序。

    @param sqlite_store: SQLite 持久化存储实例
    @type  sqlite_store: SQLiteStore
    @param chroma_store: ChromaDB 向量存储实例
    @type  chroma_store: ChromaStore
    @param embedder: Embedding 模型实例
    @type  embedder: EmbeddingModel
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        chroma_store: ChromaStore,
        embedder: EmbeddingModel,
        config: dict | None = None,
        query_rewriter: QueryRewriter | None = None,
    ):
        """构造方法

        @param sqlite_store: SQLite 持久化存储实例
        @type  sqlite_store: SQLiteStore
        @param chroma_store: ChromaDB 向量存储实例
        @type  chroma_store: ChromaStore
        @param embedder: Embedding 模型实例
        @type  embedder: EmbeddingModel
        @param config: 检索配置字典, 若为 None 则从 settings 读取
        @type  config: dict | None
        @param query_rewriter: 查询改写器实例, 为 None 时不进行查询改写
        @type  query_rewriter: QueryRewriter | None, optional
        """
        self.sqlite_store = sqlite_store
        self.chroma_store = chroma_store
        self.embedder = embedder
        if not isinstance(embedder, EmbeddingModel):
            raise TypeError(
                f"embedder 必须是 EmbeddingModel 的子类，实际类型: {type(embedder).__name__}"
            )

        self.query_rewriter = query_rewriter
        if query_rewriter is not None and not isinstance(query_rewriter, QueryRewriter):
            raise TypeError(
                f"query_rewriter 必须是 QueryRewriter 的实例，实际类型: {type(query_rewriter).__name__}"
            )

        # 加载 RRF 配置（防御性读取: 缺失时使用默认值）
        if config is None:
            from zrag.settings import ZRAG_RETRIEVAL
            config = ZRAG_RETRIEVAL
        self.rrf_k = float(config.get('rrf_k', 60))
        w = config.get('rrf_weights', {})
        self.w_vector = float(w.get('vector', 1.0))
        self.w_keyword = float(w.get('keyword', 1.0))

    def hybrid_search(self, query: str, k: int = 10) -> list[SearchResult]:
        """混合检索: ChromaDB 向量检索 + SQLite FTS5 关键词检索 -> RRF 融合

        1. embedder.embed_query(query) 获取查询向量
        2. chroma_store.similarity_search(query_vector, k) 获取向量检索结果
        3. sqlite_store.search_fts5(query, k) 获取关键词检索结果
        4. RRF 融合: score(d) = w_vector / (rrf_k + rank_vector) + w_keyword / (rrf_k + rank_bm25)
        5. 按 RRF score 降序排列, 返回 top-k

        @param query: 用户输入的查询字符串
        @type  query: str
        @param k: 返回结果的最大数量, defaults to 10
        @type  k: int, optional

        @return: 按 RRF 融合分数降序排列的检索结果列表,
                 每个结果包含 chunk_id / content / doc_title / source_id / source_type / score
        @type:   list[SearchResult]
        """
        if self.query_rewriter is not None:
            rewritten = self.query_rewriter.rewrite(query)
            fts5_query = rewritten['keywords']
            vector_query = rewritten['refined_query']
        else:
            fts5_query = query
            vector_query = query

        query_vector = self.embedder.embed_query(vector_query)
        expand_k = k * 2
        vector_results = self.chroma_store.similarity_search(query_vector, expand_k)
        keyword_results = self.sqlite_store.search_fts5(fts5_query, expand_k)

        vector_ranks = self._build_vector_ranks(vector_results)
        keyword_ranks = self._build_keyword_ranks(keyword_results)

        rrf_scores = self._compute_rrf_scores(vector_ranks, keyword_ranks)

        return self._build_results(
            vector_results, keyword_results, rrf_scores, k,
        )

    @staticmethod
    def _build_vector_ranks(vector_results: list[dict]) -> dict[str, int]:
        """为向量检索结果分配排名

        向量结果按 distance 升序排列（distance 越小越相似）,
        排名从 1 开始。

        @param vector_results: ChromaStore.similarity_search 返回的结果列表
        @type  vector_results: list[dict]

        @return: chunk_id -> rank 的映射字典
        @type:   dict[str, int]
        """
        return {
            vr['id']: i + 1
            for i, vr in enumerate(vector_results)
        }

    @staticmethod
    def _build_keyword_ranks(keyword_results: list[dict]) -> dict[str, int]:
        """为关键词检索结果分配排名

        SQLite FTS5 结果已按 bm25_score 升序排列（bm25 值越小越相关）,
        排名从 1 开始。

        @param keyword_results: SQLiteStore.search_fts5 返回的结果列表
        @type  keyword_results: list[dict]

        @return: chunk_id -> rank 的映射字典
        @type:   dict[str, int]
        """
        return {
            kr['chunk_id']: i + 1
            for i, kr in enumerate(keyword_results)
        }

    def _compute_rrf_scores(
        self,
        vector_ranks: dict[str, int],
        keyword_ranks: dict[str, int],
    ) -> dict[str, float]:
        """计算 RRF 融合分数

        RRF 公式: score(d) = w_vector / (rrf_k + rank_vector) + w_keyword / (rrf_k + rank_bm25)
        若某篇文档仅出现在一个检索方式中, 则另一个 rank 视为无穷大,
        对应分数项为 0。

        @param vector_ranks: chunk_id -> 向量检索排名
        @type  vector_ranks: dict[str, int]
        @param keyword_ranks: chunk_id -> 关键词检索排名
        @type  keyword_ranks: dict[str, int]

        @return: chunk_id -> RRF 融合分数的映射字典
        @type:   dict[str, float]
        """
        all_chunk_ids = set(vector_ranks.keys()) | set(keyword_ranks.keys())
        scores: dict[str, float] = {}
        for chunk_id in all_chunk_ids:
            rank_v = vector_ranks.get(chunk_id, float('inf'))
            rank_k = keyword_ranks.get(chunk_id, float('inf'))
            score = self.w_vector / (self.rrf_k + rank_v) + self.w_keyword / (self.rrf_k + rank_k)
            scores[chunk_id] = score
        return scores

    def _build_results(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        rrf_scores: dict[str, float],
        k: int,
    ) -> list[SearchResult]:
        """构建最终检索结果列表

        优先从 keyword_results 获取 chunk 的完整信息（含 content / doc_title）,
        对仅在 vector_results 中出现的 chunk, 通过 SQLite 补充文档信息。

        @param vector_results: ChromaStore.similarity_search 返回的结果列表
        @type  vector_results: list[dict]
        @param keyword_results: SQLiteStore.search_fts5 返回的结果列表
        @type  keyword_results: list[dict]
        @param rrf_scores: chunk_id -> RRF 融合分数的映射字典
        @type  rrf_scores: dict[str, float]
        @param k: 返回结果的最大数量
        @type  k: int

        @return: 按 RRF score 降序排列的检索结果列表
        @type:   list[SearchResult]
        """
        result_map: dict[str, SearchResult] = {}
        path_a_count = 0
        path_b_count = 0

        # 优先从 keyword_results 获取完整信息
        for kr in keyword_results:
            cid = kr['chunk_id']
            result_map[cid] = SearchResult(
                chunk_id=cid,
                content=kr['content'],
                doc_title=kr['doc_title'],
                source_id=kr['source_id'],
                source_type=kr['source_type'],
                score=rrf_scores.get(cid, 0.0),
                chunk_index=kr.get('chunk_index'),
            )
            path_a_count += 1
            logger.info(
                "Path A (keyword): chunk_id=%s doc_title=%s score=%.4f",
                cid, kr['doc_title'], rrf_scores.get(cid, 0.0),
            )

        # 对仅在 vector_results 中出现的 chunk_id, 尝试通过 SQLite 补充信息
        for vr in vector_results:
            cid = vr['id']
            if cid not in result_map:
                row = self.sqlite_store.fetch_one(
                    "SELECT * FROM chunks WHERE chunk_id = ?",
                    (cid,),
                )
                if row is not None:
                    result_map[cid] = SearchResult(
                        chunk_id=cid,
                        content=row['content'],
                        doc_title=row['doc_title'],
                        source_id=row['source_id'],
                        source_type=row['source_type'],
                        score=rrf_scores.get(cid, 0.0),
                        chunk_index=row.get('chunk_index'),
                    )
                    path_b_count += 1
                    logger.info(
                        "Path B (vector+SQLite): chunk_id=%s doc_title=%s score=%.4f",
                        cid, row['doc_title'], rrf_scores.get(cid, 0.0),
                    )
                else:
                    meta = vr['metadata']
                    logger.warning(
                        "Path C (skip): chunk_id=%s not found in SQLite, "
                        "metadata_keys=%s, skipping",
                        cid,
                        list(meta.keys()) if meta else [],
                    )
                    continue

        logger.info(
            "_build_results: total=%d (path_a=%d path_b=%d) k=%d",
            len(result_map), path_a_count, path_b_count, k,
        )

        results = sorted(result_map.values(), key=lambda r: r.score, reverse=True)
        return results[:k]
