"""切片 2 — SQLiteStore CRUD"""
import pytest
from zrag.models.document import Chunk, RawDocument


def _make_store():
    """创建内存 SQLiteStore 并建表"""
    from zrag.store.sqlite_store import SQLiteStore
    store = SQLiteStore(':memory:')
    store.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            doc_title TEXT,
            content TEXT NOT NULL,
            chunk_index INTEGER
        )
    """)
    store.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content, content=chunks, content_rowid=rowid
        )
    """)
    store.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
        END
    """)
    store.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
        END
    """)
    store.execute("""
        CREATE TABLE IF NOT EXISTS processed_docs (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )
    """)
    return store


class TestAddChunks:
    def test_add_then_query(self):
        """写入 chunk → 能通过 fetch_one 查到"""
        store = _make_store()
        store.add_chunks([
            Chunk('t_0', 'test', 'type', 'Doc', 'Hello', 0),
        ])
        row = store.fetch_one("SELECT chunk_id, content FROM chunks WHERE chunk_id = ?", ('t_0',))
        assert row is not None
        assert row['content'] == 'Hello'


class TestDeleteBySource:
    def test_delete_removes_chunks(self):
        """delete_by_source → chunks 被删除"""
        store = _make_store()
        store.add_chunks([
            Chunk('a_0', 'src_a', 't', 'A', 'aa', 0),
            Chunk('b_0', 'src_b', 't', 'B', 'bb', 0),
        ])
        store.delete_by_source('src_a')
        remaining = store.fetch_all("SELECT chunk_id FROM chunks")
        assert [r['chunk_id'] for r in remaining] == ['b_0']


class TestProcessedDocs:
    def test_get_nonexistent(self):
        """get_processed(不存在) → None"""
        store = _make_store()
        assert store.get_processed('xyz') is None

    def test_upsert_creates(self):
        """upsert_processed → 新增记录"""
        store = _make_store()
        doc = RawDocument('src1', 'notes', 'content', 'hash123')
        store.upsert_processed(doc)
        row = store.get_processed('src1')
        assert row is not None
        assert row['source_type'] == 'notes'
        assert row['content_hash'] == 'hash123'

    def test_upsert_updates(self):
        """upsert_processed → 更新已有记录"""
        store = _make_store()
        store.upsert_processed(RawDocument('s1', 't', 'c1', 'old_hash'))
        store.upsert_processed(RawDocument('s1', 't', 'c2', 'new_hash'))
        row = store.get_processed('s1')
        assert row['content_hash'] == 'new_hash'


class TestSearchFTS5:
    def test_match_found(self):
        """search_fts5 → 命中匹配内容"""
        store = _make_store()
        store.add_chunks([
            Chunk('m_0', 'src', 't', 'Doc', 'Python 机器学习基础', 0),
            Chunk('m_1', 'src', 't', 'Doc', 'Java Spring 框架', 0),
        ])
        results = store.search_fts5('Python', k=10)
        chunk_ids = [r['chunk_id'] for r in results]
        assert 'm_0' in chunk_ids

    def test_no_match(self):
        """search_fts5 → 不匹配返回空列表"""
        store = _make_store()
        store.add_chunks([
            Chunk('n_0', 'src', 't', 'Doc', 'Apple Banana', 0),
        ])
        results = store.search_fts5('Zebra', k=10)
        assert results == []


class TestTransaction:
    def test_commit(self):
        """transaction 提交 → 数据持久化"""
        store = _make_store()
        with store.transaction() as db:
            db.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                ('tx_0', 'src', 't', 'Doc', 'data', 0),
            )
        row = store.fetch_one("SELECT chunk_id FROM chunks WHERE chunk_id = ?", ('tx_0',))
        assert row is not None

    def test_rollback(self):
        """transaction 失败 → 回滚"""
        store = _make_store()
        with store.transaction() as db:
            db.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                ('rb_0', 'src', 't', 'Doc', 'data', 0),
            )
        with pytest.raises(ValueError):
            with store.transaction() as db:
                db.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                    ('rb_1', 'src', 't', 'Doc', 'data', 0),
                )
                raise ValueError("rollback!")
        row = store.fetch_one("SELECT chunk_id FROM chunks WHERE chunk_id = ?", ('rb_1',))
        assert row is None
