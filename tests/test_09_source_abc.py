"""测试切片 8 — DocumentSource ABC"""
import pytest

from zrag.ingest.sources.base import DocumentSource
from zrag.models.document import RawDocument


class FakeSource(DocumentSource):
    """DocumentSource 的桩实现, 用于测试具体子类可实例化"""

    def __init__(self):
        self._docs = [
            RawDocument("id1", "test", "内容1", "hash1"),
            RawDocument("id2", "test", "内容2", "hash2"),
        ]

    def fetch_batch(self, batch_size=10):
        for i in range(0, len(self._docs), batch_size):
            yield self._docs[i:i + batch_size]

    @property
    def source_type(self):
        return "fake_test"


class IncompleteSource(DocumentSource):
    """未实现 fetch_batch 方法的子类, 用于测试抽象方法检查"""

    @property
    def source_type(self):
        return "incomplete"


class EmptySource(DocumentSource):
    """空数据源的桩实现, 用于测试空源不 yield 任何内容"""

    def fetch_batch(self, batch_size=10):
        return iter([])

    @property
    def source_type(self):
        return "empty"


class TestDocumentSourceABC:
    """DocumentSource 抽象基类测试"""

    def test_cannot_instantiate_abc(self):
        """DocumentSource 是 ABC, 不能直接实例化, 应抛出 TypeError"""
        with pytest.raises(TypeError):
            DocumentSource()

    def test_concrete_implementation_fetch(self):
        """实现 fetch_batch 的子类可正常迭代获取文档"""
        source = FakeSource()

        count = 0
        for batch in source.fetch_batch():
            for doc in batch:
                count += 1
                assert isinstance(doc, RawDocument)

        assert count == 2

    def test_concrete_implementation_source_type(self):
        """实现 source_type 的子类返回正确标识"""
        source = FakeSource()

        assert source.source_type == "fake_test"

    def test_fetch_batch_empty(self):
        """空数据源的 fetch_batch 不 yield 任何内容"""
        source = EmptySource()

        for batch in source.fetch_batch():
            assert False, "不应 yield 任何内容, 但得到了: " + str(batch)

    def test_missing_method_raises(self):
        """未实现 fetch_batch 抽象方法的子类, 实例化时抛出 TypeError"""
        with pytest.raises(TypeError):
            IncompleteSource()

    def test_fetch_batch_batch_size(self):
        """验证 batch_size 参数生效"""
        source = FakeSource()

        batches = list(source.fetch_batch(batch_size=1))
        assert len(batches) == 2
        assert len(batches[0]) == 1
        assert batches[0][0].source_id == "id1"
        assert len(batches[1]) == 1
        assert batches[1][0].source_id == "id2"
