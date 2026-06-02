import sqlite3
from contextlib import contextmanager
from typing import Any

from zrag.models.document import Chunk


class SQLiteStore:
    """SQLite 存储操作封装类

    提供对 SQLite 数据库的 CRUD 操作、事务管理以及 FTS5 全文搜索能力。
    作为 ZRAG 系统的可信数据源, 负责 chunks、FTS5 索引和 processed_docs 的持久化管理。
    连接采用懒加载方式, 首次调用时自动建立连接。

    调用者无需直接管理连接生命周期, 但在使用完毕后建议调用 close() 方法释放资源。
    """

    def __init__(self, db_path: str = 'data/zrag.db'):
        """构造方法

        @param db_path: SQLite 数据库文件路径, defaults to 'data/zrag.db'
                        若传入 ':memory:' 则创建内存数据库, 主要用于测试场景
        @type  db_path: str, optional
        """
        self._db_path = db_path
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
        该方法不会自动提交事务, 调用者需要视情况包裹在 transaction() 上下文中。
        FTS5 索引通过 SQLite 触发器自动同步更新。

        @param chunks: 待写入的分块对象列表
        @type  chunks: list[Chunk]

        @raises: 当 chunks 表中存在相同 chunk_id 时触发
        @type:   sqlite3.IntegrityError
        """
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO chunks (chunk_id, source_id, source_type, doc_title, content, chunk_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(c.chunk_id, c.source_id, c.source_type, c.doc_title, c.content, c.chunk_index)
             for c in chunks],
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
        查询语法遵循 SQLite FTS5 的 MATCH 语法, 支持 AND/OR/NOT 等布尔操作。

        @param query: 用户输入的搜索查询字符串
        @type  query: str
        @param k: 返回结果的最大数量, defaults to 10
        @type  k: int, optional

        @return: 搜索结果列表, 每条包含 chunks 表的所有字段及 bm25_score 评分
        @type:   list[dict]
        """
        return self.fetch_all(
            """SELECT c.*, bm25(chunks_fts) AS bm25_score
               FROM chunks_fts
               JOIN chunks c ON c.rowid = chunks_fts.rowid
               WHERE chunks_fts MATCH ?
               ORDER BY bm25(chunks_fts)
               LIMIT ?""",
            (query, k),
        )

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

    def close(self) -> None:
        """关闭数据库连接

        释放当前持有的 SQLite 连接资源。
        建议在应用退出或连接不再需要时调用。
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None
