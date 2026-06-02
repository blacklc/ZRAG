import sqlite3
from contextlib import contextmanager
from typing import Any

from zrag.models.document import Chunk


class SQLiteStore:
    """SQLite 存储封装 — 提供 CRUD、事务、FTS5 搜索"""

    def __init__(self, db_path: str = 'data/zrag.db'):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        row = self._get_conn().execute(sql, params).fetchone()
        if row is None:
            return None
        return dict(row)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self._get_conn().execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def add_chunks(self, chunks: list[Chunk]) -> None:
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO chunks (chunk_id, source_id, source_type, doc_title, content, chunk_index) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(c.chunk_id, c.source_id, c.source_type, c.doc_title, c.content, c.chunk_index)
             for c in chunks],
        )

    def delete_by_source(self, source_id: str) -> None:
        self.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))

    def get_processed(self, source_id: str) -> dict | None:
        return self.fetch_one(
            "SELECT * FROM processed_docs WHERE source_id = ?", (source_id,),
        )

    def upsert_processed(self, doc: Any) -> None:
        self.execute(
            "INSERT OR REPLACE INTO processed_docs (source_id, source_type, content_hash, imported_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (doc.source_id, doc.source_type, doc.content_hash),
        )

    def search_fts5(self, query: str, k: int = 10) -> list[dict]:
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
        conn = self._get_conn()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
