"""测试切片 6 — EmbeddingModel ABC"""
import pytest
from zrag.embed.base import EmbeddingModel


class FakeEmbedder(EmbeddingModel):
    """EmbeddingModel 的桩实现, 用于测试具体子类可实例化"""

    def embed(self, texts):
        return [[0.0] * 64 for _ in texts]

    def embed_query(self, query):
        return [0.0] * 64

    @property
    def dimension(self):
        return 64


class IncompleteEmbedder(EmbeddingModel):
    """未实现 embed 方法的子类, 用于测试抽象方法检查"""

    def embed_query(self, query):
        return [0.0] * 64

    @property
    def dimension(self):
        return 64


class TestEmbeddingModelABC:
    """EmbeddingModel 抽象基类测试"""

    def test_cannot_instantiate_abc(self):
        """EmbeddingModel 是 ABC, 不能直接实例化, 应抛出 TypeError"""
        with pytest.raises(TypeError):
            EmbeddingModel()

    def test_concrete_implementation_works(self):
        """实现全部抽象方法的子类可以实例化且方法可调用"""
        embedder = FakeEmbedder()

        result = embedder.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 64
        assert all(v == 0.0 for v in result[0])

        query_vec = embedder.embed_query("test query")
        assert len(query_vec) == 64
        assert all(v == 0.0 for v in query_vec)

        assert embedder.dimension == 64

    def test_missing_method_raises(self):
        """未实现某个抽象方法的子类, 实例化时抛出 TypeError"""
        with pytest.raises(TypeError):
            IncompleteEmbedder()
