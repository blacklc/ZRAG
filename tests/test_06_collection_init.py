"""切片 5 — ChromaDB Collection 管理"""

import tempfile

from zrag.store.vector_store import ChromaStore


def test_init_collection_creates_collection():
    """init_collection() 后 add + count == 1, collection 可用"""
    with tempfile.TemporaryDirectory() as tmp:
        store = ChromaStore(persist_dir=tmp)
        # collection 初始为 None
        assert store._collection is None
        store.init_collection()
        # init_collection 后 collection 不为 None
        assert store._collection is not None

        store.add(
            ids=['vec_0'],
            embeddings=[[1.0, 0.0, 0.0]],
            metadatas=[{'source_id': 'doc_a', 'source_type': 'notes'}],
        )
        assert store.count() == 1


def test_init_collection_idempotent():
    """两次调用 init_collection() 不报错"""
    with tempfile.TemporaryDirectory() as tmp:
        store = ChromaStore(persist_dir=tmp)
        store.init_collection()
        # 第二次调用应不抛出异常
        store.init_collection()

        # 再次确认仍可正常使用
        store.add(
            ids=['v'],
            embeddings=[[0.5, 0.5]],
            metadatas=[{'source_id': 'd'}],
        )
        assert store.count() == 1


def test_lazy_init_add():
    """不调用 init_collection() 直接 add, 内部自动初始化"""
    with tempfile.TemporaryDirectory() as tmp:
        store = ChromaStore(persist_dir=tmp)
        assert store._collection is None

        store.add(
            ids=['a', 'b'],
            embeddings=[[1.0, 0.0], [0.0, 1.0]],
            metadatas=[{'source_id': 'x'}, {'source_id': 'y'}],
        )
        # add 后 collection 已自动初始化
        assert store._collection is not None
        assert store.count() == 2


def test_lazy_init_search():
    """不调用 init_collection() 直接 search, 返回空结果"""
    with tempfile.TemporaryDirectory() as tmp:
        store = ChromaStore(persist_dir=tmp)
        assert store._collection is None

        results = store.similarity_search([1.0, 0.0, 0.0], k=5)
        # 空集合返回空列表
        assert results == []
        # search 后 collection 已自动初始化
        assert store._collection is not None


def test_lazy_init_count():
    """不调用 init_collection() 直接 count, 返回 0"""
    with tempfile.TemporaryDirectory() as tmp:
        store = ChromaStore(persist_dir=tmp)
        assert store._collection is None

        cnt = store.count()
        assert cnt == 0
        # count 后 collection 已自动初始化
        assert store._collection is not None


def test_multiple_stores_independent():
    """两个不同目录的 ChromaStore 互相隔离"""
    with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
        store1 = ChromaStore(persist_dir=tmpdir1)
        store2 = ChromaStore(persist_dir=tmpdir2)

        store1.add(
            ids=['s1_only'],
            embeddings=[[1.0, 0.0]],
            metadatas=[{'source_id': 'doc_1'}],
        )
        store2.add(
            ids=['s2_only'],
            embeddings=[[0.0, 1.0]],
            metadatas=[{'source_id': 'doc_2'}],
        )

        assert store1.count() == 1
        assert store2.count() == 1

        # 互不干扰
        r1 = store1.similarity_search([1.0, 0.0], k=5)
        assert r1[0]['id'] == 's1_only'

        r2 = store2.similarity_search([0.0, 1.0], k=5)
        assert r2[0]['id'] == 's2_only'
