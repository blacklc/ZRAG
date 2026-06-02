"""切片 4 — SQLiteStore 建表初始化"""
import pytest


def _make_store():
    """创建内存 SQLiteStore"""
    from zrag.store.sqlite_store import SQLiteStore
    store = SQLiteStore(':memory:')
    return store


def _build_and_check_tables(store):
    """辅助方法：调用 init_db() 并返回表名集合"""
    store.init_db()
    rows = store.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return {r['name'] for r in rows}


class TestInitDB:
    def test_all_tables_created(self):
        """init_db 后确认 5 张业务表都存在"""
        store = _make_store()
        tables = _build_and_check_tables(store)

        expected = {'chunks', 'chunks_fts', 'processed_docs', 'conversations', 'messages'}
        assert expected.issubset(tables), f"缺少表: {expected - tables}"

    def test_idempotent(self):
        """连续调用两次 init_db 不报错"""
        store = _make_store()
        store.init_db()
        # 第二次调用应不抛出异常
        store.init_db()
        # 验证数据表仍正常可用
        tables = _build_and_check_tables(store)
        assert 'chunks' in tables
        assert 'conversations' in tables

    def test_fts5_trigger_works(self):
        """init_db → INSERT chunk → FTS5 命中搜索"""
        store = _make_store()
        store.init_db()
        store.execute(
            "INSERT INTO chunks (chunk_id, source_id, source_type, doc_title, content, chunk_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ('fts_0', 'src', 'note', 'Doc', 'Python 机器学习测试', 0),
        )
        results = store.fetch_all(
            "SELECT rowid, content FROM chunks_fts WHERE chunks_fts MATCH ?",
            ('Python',),
        )
        assert len(results) >= 1
        assert 'Python 机器学习测试' in results[0]['content']

    def test_trigger_sync_on_delete(self):
        """DELETE chunk → FTS5 索引同步删除"""
        store = _make_store()
        store.init_db()
        store.execute(
            "INSERT INTO chunks (chunk_id, source_id, source_type, doc_title, content, chunk_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ('del_0', 'src_del', 'note', 'Doc', 'delete test content for FTS sync', 0),
        )
        # 确认插入后 FTS5 有内容
        before = store.fetch_all(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?",
            ('delete',),
        )
        assert len(before) == 1

        # 删除 chunk
        store.execute("DELETE FROM chunks WHERE source_id = ?", ('src_del',))

        # FTS5 索引应同步删除
        after = store.fetch_all(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?",
            ('delete',),
        )
        assert len(after) == 0

    def test_tables_have_expected_schema(self):
        """检查各表的列名和类型匹配设计"""
        store = _make_store()
        store.init_db()

        # 检查 chunks 表的列
        chunk_cols = store.fetch_all("PRAGMA table_info(chunks)")
        chunk_col_map = {r['name']: r['type'] for r in chunk_cols}
        for col_name, col_type in [
            ('chunk_id', 'TEXT'),
            ('source_id', 'TEXT'),
            ('source_type', 'TEXT'),
            ('doc_title', 'TEXT'),
            ('content', 'TEXT'),
            ('chunk_index', 'INTEGER'),
            ('created_at', 'TEXT'),
        ]:
            assert col_name in chunk_col_map, f"chunks 表缺少列: {col_name}"
            assert chunk_col_map[col_name].upper() == col_type, (
                f"chunks.{col_name} 类型应为 {col_type}, 实际为 {chunk_col_map[col_name]}"
            )

        # 检查 processed_docs 表的列
        pd_cols = store.fetch_all("PRAGMA table_info(processed_docs)")
        pd_col_map = {r['name']: r['type'] for r in pd_cols}
        for col_name, col_type in [
            ('source_id', 'TEXT'),
            ('source_type', 'TEXT'),
            ('content_hash', 'TEXT'),
            ('imported_at', 'TEXT'),
        ]:
            assert col_name in pd_col_map, f"processed_docs 表缺少列: {col_name}"

        # 检查 conversations 表的列
        conv_cols = store.fetch_all("PRAGMA table_info(conversations)")
        conv_col_map = {r['name']: r['type'] for r in conv_cols}
        for col_name, col_type in [
            ('id', 'TEXT'),
            ('title', 'TEXT'),
            ('created_at', 'TEXT'),
        ]:
            assert col_name in conv_col_map, f"conversations 表缺少列: {col_name}"

        # 检查 messages 表的列
        msg_cols = store.fetch_all("PRAGMA table_info(messages)")
        msg_col_map = {r['name']: r['type'] for r in msg_cols}
        for col_name, col_type in [
            ('id', 'TEXT'),
            ('conversation_id', 'TEXT'),
            ('role', 'TEXT'),
            ('content', 'TEXT'),
            ('sources', 'TEXT'),
            ('created_at', 'TEXT'),
        ]:
            assert col_name in msg_col_map, f"messages 表缺少列: {col_name}"

    def test_indices_created(self):
        """检查所需索引都存在"""
        store = _make_store()
        store.init_db()

        rows = store.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        idx_names = {r['name'] for r in rows}

        expected_indices = {
            'idx_chunks_source_id',
            'idx_chunks_source_type',
            'idx_processed_source_type',
            'idx_messages_conv_id',
            'idx_messages_created',
        }
        missing = expected_indices - idx_names
        assert not missing, f"缺少索引: {missing}"
