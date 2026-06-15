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


class TestTokenizeText:
    """_tokenize_text() 单元测试"""

    def setup_method(self):
        from zrag.store.sqlite_store import _tokenize_text
        self.tokenize = _tokenize_text

    def test_chinese_tokenized(self):
        """中文文本被 jieba 分词"""
        result = self.tokenize("中文分词测试")
        tokens = result.split()
        assert len(tokens) >= 3  # 至少 '中文' '分词' '测试'

    def test_english_preserved(self):
        """英文和代码部分保留原样"""
        result = self.tokenize("hello world treeIndex")
        assert "hello" in result
        assert "treeIndex" in result

    def test_mixed_chinese_english(self):
        """中英混合文本正确处理"""
        result = self.tokenize("etcd的MVCC模块由treeIndex和Backend组成")
        assert "etcd" in result
        assert "treeIndex" in result
        # 中文部分应被分词
        tokens = result.split()
        assert len(tokens) > 5

    def test_empty_string(self):
        """空字符串返回空"""
        result = self.tokenize("")
        assert result == ""

    def test_tokenize_for_fts5_write(self):
        """验证 FTS5 写入时的 content 经过分词处理"""
        text = "etcd的MVCC模块"
        result = self.tokenize(text)
        # 分词后应为空格分隔的 token 串
        assert "MVCC" in result
        assert "etcd" in result
        tokens = result.split()
        assert len(tokens) >= 4  # etcd, 的, MVCC, 模块 等

    def test_tokenize_for_fts5_query(self):
        """验证 FTS5 查询时的 query 经过相同的分词处理"""
        query = "更新操作"
        result = self.tokenize(query)
        # 查询词应被正确分词
        assert len(result.split()) >= 2  # 更新, 操作

    def test_tokenize_preserves_special_chars(self):
        """分词保留对 FTS5 安全的关键字符"""
        text = "C++ and C# programming"
        result = self.tokenize(text)
        # 英文部分保留
        assert "C++" in result or "programming" in result

    def test_fts5_query_uses_tokenized_text(self):
        """验证 FTS5 查询使用 jieba 分词后的结果"""
        from zrag.store.sqlite_store import _tokenize_text, _sanitize_fts5_query

        query = "讲解一下在etcd的更新操作中"
        safe = _sanitize_fts5_query(query)
        tokenized = _tokenize_text(safe)

        # 分词后应该包含多个独立 token
        tokens = tokenized.split()
        assert len(tokens) >= 4
        assert "etcd" in tokens

    def test_fts5_query_filters_short_tokens(self):
        """验证 FTS5 查询过滤中文单字词"""
        from zrag.store.sqlite_store import _tokenize_text, _sanitize_fts5_query

        query = "我想知道etcd的更新操作"
        safe = _sanitize_fts5_query(query)
        tokenized = _tokenize_text(safe)
        tokens = tokenized.split()
        filtered = [t for t in tokens if t.isascii() or len(t) >= 2]

        # "我""想""的" 被过滤
        assert "我" not in filtered
        assert "想" not in filtered
        # "etcd" 保留（ASCII）
        assert "etcd" in filtered
        # "更新""操作" 保留（长度 >= 2）
        assert "更新" in filtered or "操作" in filtered
