import sqlite3
from contextlib import contextmanager
from typing import Any

from zrag.models.document import Chunk
import jieba


def _tokenize_text(text: str) -> str:
    """对文本做 jieba 分词，返回空格分隔的字符串

    中英混合文本：中文部分做 jieba 分词，英文/代码部分保留原样。

    @param text: 待分词文本
    @type  text: str
    @return: 分词后的空格分隔字符串
    @rtype:  str
    """
    if not text:
        return ""
    return ' '.join(jieba.cut(text))


class SQLiteStore:
    """SQLite 存储操作封装类

    提供对 SQLite 数据库的 CRUD 操作、事务管理以及 FTS5 全文搜索能力。
    作为 ZRAG 系统的可信数据源, 负责 chunks、FTS5 索引和 processed_docs 的持久化管理。
    连接采用懒加载方式, 首次调用时自动建立连接。

    调用者无需直接管理连接生命周期, 但在使用完毕后建议调用 close() 方法释放资源。
    """

    def __init__(self, db_path: str | None = None):
        """构造方法

        若 db_path 未显式传入，则从 Django settings.ZRAG_STORAGE 配置中读取。
        配置中也缺失时抛出 ValueError。

        @param db_path: SQLite 数据库文件路径, defaults to None
                        若传入 ':memory:' 则创建内存数据库, 主要用于测试场景
                        未传入则从配置 storage.sqlite_path 读取
        @type  db_path: str, optional

        @raises ValueError: db_path 在参数和配置中均未提供时抛出
        """
        if db_path is not None:
            self._db_path = db_path
        else:
            from django.conf import settings
            storage_cfg = getattr(settings, "ZRAG_STORAGE", {})
            self._db_path = storage_cfg.get("sqlite_path")
            if not self._db_path:
                raise ValueError("配置缺失: storage.sqlite_path, 请检查 config/storage.yaml")
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（懒加载）

        若当前尚未建立连接, 则创建新连接并配置 row_factory 为 sqlite3.Row
        以及启用 WAL 模式以提升并发读性能。

        @return: SQLite 数据库连接对象
        @type:   sqlite3.Connection
        """
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.isolation_level = None
        return self._conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行一条 SQL 语句

        @param sql: 要执行的 SQL 语句, 支持 ? 占位符的参数化查询
        @type  sql: str
        @param params: SQL 参数元组, 与 sql 中的 ? 占位符一一对应, defaults to ()
        @type  params: tuple, optional

        @return: SQLite 游标对象
        @type:   sqlite3.Cursor
        """
        return self._get_conn().execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """查询单行记录

        @param sql: 查询 SQL 语句
        @type  sql: str
        @param params: 查询参数, defaults to ()
        @type  params: tuple, optional

        @return: 返回查询结果的字典表示, 若未匹配到任何记录则返回 None
        @type:   dict | None
        """
        row = self._get_conn().execute(sql, params).fetchone()
        if row is None:
            return None
        return dict(row)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """查询多行记录

        @param sql: 查询 SQL 语句
        @type  sql: str
        @param params: 查询参数, defaults to ()
        @type  params: tuple, optional

        @return: 所有匹配记录的字典列表, 每行一个 dict
        @type:   list[dict]
        """
        rows = self._get_conn().execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """批量写入文档分块记录

        将多个 Chunk 对象一次性写入 chunks 表。
        FTS5 索引在插入 chunks 后以分词后内容写入 chunks_fts 表。
        该方法不会自动提交事务, 调用者需要视情况包裹在 transaction() 上下文中。

        @param chunks: 待写入的分块对象列表
        @type  chunks: list[Chunk]

        @raises: 当 chunks 表中存在相同 chunk_id 时触发
        @type:   sqlite3.IntegrityError
        """
        conn = self._get_conn()
        for c in chunks:
            cursor = conn.execute(
                "INSERT INTO chunks (chunk_id, source_id, source_type, doc_title, content, chunk_index) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (c.chunk_id, c.source_id, c.source_type, c.doc_title, c.content, c.chunk_index),
            )
            rowid = cursor.lastrowid
            # Replace trigger-inserted raw content with tokenized content for FTS5 indexing
            tokenized = _tokenize_text(c.content)
            conn.execute(
                "INSERT INTO chunks_fts(chunks_fts, rowid) VALUES('delete', ?)", (rowid,)
            )
            conn.execute(
                "INSERT INTO chunks_fts(rowid, content) VALUES(?, ?)", (rowid, tokenized)
            )

    def delete_by_source(self, source_id: str) -> None:
        """删除指定源文档的所有分块

        根据 source_id 删除 chunks 表中对应的所有记录。
        FTS5 索引通过 SQLite 触发器自动同步清理。
        通常在重新摄入某篇文档前调用, 清空旧数据。

        @param source_id: 源文档的唯一标识
        @type  source_id: str
        """
        self.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))

    def get_processed(self, source_id: str) -> dict | None:
        """查询指定文档的处理状态

        从 processed_docs 表中获取某篇文档的处理记录,
        用于增量同步时判断该文档是否需要重新处理。

        @param source_id: 源文档的唯一标识
        @type  source_id: str

        @return: 处理记录字典, 包含 source_id / source_type / content_hash / imported_at;
                 若该文档尚未处理则返回 None
        @type:   dict | None
        """
        return self.fetch_one(
            "SELECT * FROM processed_docs WHERE source_id = ?", (source_id,),
        )

    def upsert_processed(self, doc: Any) -> None:
        """更新或插入文档处理进度记录

        使用 INSERT OR REPLACE 语义, 若 source_id 已存在则更新其 content_hash 和 imported_at,
        否则插入新记录。imported_at 自动设置为当前数据库时间。

        @param doc: 包含 source_id、source_type 和 content_hash 属性的文档对象
        @type  doc: RawDocument
        """
        self.execute(
            "INSERT OR REPLACE INTO processed_docs (source_id, source_type, content_hash, imported_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (doc.source_id, doc.source_type, doc.content_hash),
        )


    def search_fts5(self, query: str, k: int = 10) -> list[dict]:
        """使用 FTS5 全文搜索引擎进行关键词检索

        对用户查询进行全文搜索, 按 BM25 相关性评分排序返回前 k 条结果。
        查询字符串会先经过特殊字符清洗, 再经过 jieba 分词后传递给 FTS5 MATCH。

        @param query: 用户输入的搜索查询字符串
        @type  query: str
        @param k: 返回结果的最大数量, defaults to 10
        @type  k: int, optional

        @return: 搜索结果列表, 每条包含 chunks 表的所有字段及 bm25_score 评分
        @rtype:   list[dict]
        """
        safe_query = _sanitize_fts5_query(query)
        tokenized_query = _tokenize_text(safe_query)
        # 过滤短 token：非 ASCII 且长度 < 2 的丢弃（中文单字词如"我""想""的"无检索价值）
        tokens = tokenized_query.split()
        filtered_tokens = [t for t in tokens if t.isascii() or len(t) >= 2]
        if filtered_tokens:
            tokenized_query = ' '.join(filtered_tokens)
        try:
            return self.fetch_all(
                """SELECT c.*, bm25(chunks_fts) AS bm25_score
                   FROM chunks_fts
                   JOIN chunks c ON c.rowid = chunks_fts.rowid
                   WHERE chunks_fts MATCH ?
                   ORDER BY bm25(chunks_fts)
                   LIMIT ?""",
                (tokenized_query, k),
            )
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("FTS5 检索失败: query=%s safe_query=%s tokenized=%s", query, safe_query, tokenized_query)
            return []

    @contextmanager
    def transaction(self):
        """数据库事务上下文管理器

        提供事务的 BEGIN / COMMIT / ROLLBACK 自动管理。
        在 with 块内执行的数据库操作要么全部成功提交, 要么在异常时全部回滚。
        使用示例:

        with store.transaction() as db:
            db.execute("INSERT INTO ...", params)

        @raises: with 块内的异常会被传递, 同时触发事务回滚
        @type:   Exception
        """
        conn = self._get_conn()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def init_db(self) -> None:
        """创建或更新所有业务数据库表结构

        使用 CREATE TABLE IF NOT EXISTS 语义自动建表,
        包括 chunks / chunks_fts( FTS5 ) / processed_docs / conversations / messages 五张表。
        同时创建 FTS5 触发器及索引。
        该方法幂等——重复调用不会报错或覆盖已有数据。

        @raises: SQLite 建表或索引创建失败
        @type:   sqlite3.OperationalError
        """
        conn = self._get_conn()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id     TEXT PRIMARY KEY,
                source_id    TEXT NOT NULL,
                source_type  TEXT NOT NULL,
                doc_title    TEXT,
                content      TEXT NOT NULL,
                chunk_index  INTEGER,
                created_at   TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON chunks(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source_type ON chunks(source_type)")

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content, content=chunks, content_rowid=rowid
            )
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_docs (
                source_id     TEXT PRIMARY KEY,
                source_type   TEXT NOT NULL,
                content_hash  TEXT NOT NULL,
                imported_at   TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_source_type ON processed_docs(source_type)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                sources         TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conversation_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(conversation_id, created_at)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ingest_tasks (
                id            TEXT PRIMARY KEY,
                task_type     TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                total         INTEGER DEFAULT 0,
                processed     INTEGER DEFAULT 0,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    def close(self) -> None:
        """关闭数据库连接

        释放当前持有的 SQLite 连接资源。
        建议在应用退出或连接不再需要时调用。
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def _sanitize_fts5_query(query: str) -> str:
    """清洗 FTS5 查询字符串，转义特殊字符

    FTS5 MATCH 语法中的特殊字符（如 *、\"、(、)、? 等）会导致语法错误。
    将这些字符替换为空格，保留纯文本关键词。

    @param query: 用户原始查询
    @type  query: str

    @return: 清洗后的安全查询字符串
    @rtype:  str
    """
    import re
    # 移除 FTS5 特殊字符，仅保留中英文、数字和空格
    safe = re.sub(r'[^\w一-鿿\s]', ' ', query)
    # 压缩多余空白
    safe = re.sub(r'\s+', ' ', safe).strip()
    return safe


# === 模块级单例 ===
_sqlite_store: 'SQLiteStore | None' = None

def get_sqlite_store(db_path: str | None = None) -> SQLiteStore:
    """获取 SQLiteStore 单例实例

    使用模块级全局变量缓存 SQLiteStore 实例, 确保整个应用生命周期内只创建一个实例。
    若首次调用时实例尚未创建, 则根据传入的 db_path 或配置路径创建新实例。
    后续调用会忽略 db_path 参数, 直接返回已缓存的实例。

    @param db_path: 数据库文件路径, 仅在首次创建实例时生效, defaults to None
                    未传入则从配置 storage.sqlite_path 读取
    @type  db_path: str, optional

    @return: SQLiteStore 单例实例
    @type:   SQLiteStore
    """
    global _sqlite_store
    if _sqlite_store is None:
        if db_path is None:
            from django.conf import settings
            storage_cfg = getattr(settings, "ZRAG_STORAGE", {})
            db_path = storage_cfg.get("sqlite_path") or "data/zrag.db"
        _sqlite_store = SQLiteStore(db_path)
    return _sqlite_store
