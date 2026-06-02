"""测试 BgeSmallEmbedder 本地 Embedding 实现

使用 sentence-transformers 实际加载 BAAI/bge-small-zh-v1.5 模型进行向量化验证。
注意: 首次运行需要下载模型（约 250MB），后继使用缓存提速。
"""
import pytest

from zrag.embed.local import BgeSmallEmbedder


@pytest.fixture(scope="module")
def embedder() -> BgeSmallEmbedder:
    """返回 BgeSmallEmbedder 实例, 整个模块共享以复用模型加载"""
    return BgeSmallEmbedder()


class TestBgeSmallEmbedder:
    """BgeSmallEmbedder 功能测试"""

    def test_embed_returns_correct_shape(self, embedder: BgeSmallEmbedder):
        """embed 返回的列表长度等于输入文本数, 每个向量维度为 512"""
        texts = ["你好世界", "什么是 RAG", "测试文本"]
        vectors = embedder.embed(texts)
        assert len(vectors) == len(texts)
        for vec in vectors:
            assert len(vec) == 512

    def test_embed_query_returns_512d(self, embedder: BgeSmallEmbedder):
        """embed_query 返回 512 维向量"""
        vector = embedder.embed_query("测试查询")
        assert len(vector) == 512

    def test_embed_query_consistency(self, embedder: BgeSmallEmbedder):
        """同一查询两次调用返回的向量应一致（相同输入 → 相同输出）"""
        query = "确定性测试"
        v1 = embedder.embed_query(query)
        v2 = embedder.embed_query(query)
        assert v1 == v2

    def test_dimension_property(self, embedder: BgeSmallEmbedder):
        """dimension 属性返回 512"""
        assert embedder.dimension == 512
