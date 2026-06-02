"""切片 3 — ChromaDB CRUD — Tracer Bullet"""
import pytest
import tempfile


@pytest.fixture
def store():
    """每个测试使用独立的临时目录"""
    from zrag.store.vector_store import ChromaStore
    with tempfile.TemporaryDirectory() as tmp:
        yield ChromaStore(persist_dir=tmp)


class TestAddAndSearch:
    def test_add_then_search_returns_similar(self, store):
        """写入向量 → similarity_search 返回最相似的结果"""
        store.add(
            ids=['vec_0', 'vec_1'],
            embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            metadatas=[
                {'source_id': 'doc_a', 'source_type': 'notes'},
                {'source_id': 'doc_b', 'source_type': 'notes'},
            ],
        )
        results = store.similarity_search([1.0, 0.0, 0.0], k=5)
        assert len(results) >= 1
        assert results[0]['id'] == 'vec_0'

    def test_distance_ordering(self, store):
        """相似度搜索按距离升序排列（距离越小越相似）"""
        store.add(
            ids=['same_dir', 'opposite_dir', 'orthogonal'],
            embeddings=[[0.9, 0.1], [-0.5, 0.5], [0.0, 1.0]],
            metadatas=[{'source_id': 'a'}, {'source_id': 'b'}, {'source_id': 'c'}],
        )
        results = store.similarity_search([1.0, 0.0], k=3)
        assert results[0]['id'] == 'same_dir'
        assert results[0]['distance'] <= results[1]['distance']


class TestSearchLimit:
    def test_k_limits_results(self, store):
        """k=2 → 只返回 2 条结果"""
        store.add(
            ids=[str(i) for i in range(5)],
            embeddings=[[float(i), 0.0] for i in range(5)],
            metadatas=[{'source_id': 'd'} for _ in range(5)],
        )
        results = store.similarity_search([0.0, 0.0], k=2)
        assert len(results) == 2


class TestDeleteBySource:
    def test_delete_removes_vector(self, store):
        """delete_by_source → 该源文档的向量被删除"""
        store.add(
            ids=['a_0', 'a_1', 'b_0'],
            embeddings=[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]],
            metadatas=[
                {'source_id': 'doc_a'},
                {'source_id': 'doc_a'},
                {'source_id': 'doc_b'},
            ],
        )
        store.delete_by_source('doc_a')
        results = store.similarity_search([0.0, 0.0], k=10)
        ids = [r['id'] for r in results]
        assert 'b_0' in ids
        assert 'a_0' not in ids
        assert 'a_1' not in ids


class TestCount:
    def test_count_after_add(self, store):
        """添加后 count 返回正确数量"""
        store.add(
            ids=['x', 'y', 'z'],
            embeddings=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
            metadatas=[{'source_id': 'd'} for _ in range(3)],
        )
        assert store.count() == 3

    def test_empty_collection(self, store):
        """空集合 → count=0"""
        assert store.count() == 0


class TestEmptyAdd:
    def test_add_empty_list_no_error(self, store):
        """添加空列表 → 不报错"""
        store.add(ids=[], embeddings=[], metadatas=[])
        assert store.count() == 0
