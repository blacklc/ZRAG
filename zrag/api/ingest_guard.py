"""摄入并发锁模块

基于 SQLite ingest_lock 表实现原子锁, 确保同一时间只有一个摄入流程在执行。
"""

from zrag.store.sqlite_store import SQLiteStore


class IngestGuard:
    """摄入并发锁

    基于 SQLite 的 ingest_lock 表实现原子 UPDATE 锁。
    确保同一时间只有一个摄入流程在执行。

    @param store: SQLiteStore 实例
    @type  store: SQLiteStore
    """

    LOCK_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS ingest_lock (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_running INTEGER NOT NULL DEFAULT 0,
            locked_at TEXT
        )
    """

    def __init__(self, store: SQLiteStore):
        """构造方法

        接收 SQLiteStore 实例并初始化 ingest_lock 表。

        @param store: SQLiteStore 实例
        @type  store: SQLiteStore
        """
        self.store = store
        self._init_table()

    def _init_table(self):
        """初始化 ingest_lock 表

        创建 ingest_lock 表（若不存在）, 并确保初始行存在。

        @raises: SQLite 操作失败
        @type:   sqlite3.OperationalError
        """
        self.store.execute(self.LOCK_TABLE_SQL)
        # 确保初始行存在
        self.store.execute(
            "INSERT OR IGNORE INTO ingest_lock (id, is_running) VALUES (1, 0)"
        )

    def acquire(self) -> bool:
        """尝试获取锁

        通过原子 UPDATE SET is_running=1 WHERE id=1 AND is_running=0 实现。
        rowcount 返回 1 表示成功获取, 0 表示已被占用。

        @return: 是否成功获取锁
        @type:   bool
        """
        cursor = self.store.execute(
            "UPDATE ingest_lock SET is_running=1, locked_at=datetime('now') "
            "WHERE id=1 AND is_running=0"
        )
        return cursor.rowcount > 0

    def release(self):
        """释放锁

        将 is_running 恢复为 0, 允许后续 acquire 成功。
        """
        self.store.execute(
            "UPDATE ingest_lock SET is_running=0 WHERE id=1"
        )
