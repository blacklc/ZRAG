"""切片 23 — IngestGuard 测试

测试基于 SQLite 的摄入并发锁功能。
"""

from zrag.store.sqlite_store import SQLiteStore
from zrag.api.ingest_guard import IngestGuard


class TestIngestGuard:
    """IngestGuard 测试类"""

    def _make_in_memory_store(self) -> SQLiteStore:
        """创建内存 SQLiteStore 实例

        @return: 内存模式的 SQLiteStore 实例
        @rtype:  SQLiteStore
        """
        return SQLiteStore(":memory:")

    def test_init_creates_table(self):
        """初始化后表存在, 且有初始行"""
        store = self._make_in_memory_store()
        _guard = IngestGuard(store)

        row = store.fetch_one("SELECT * FROM ingest_lock WHERE id = 1")
        assert row is not None
        assert row["is_running"] == 0
        assert row["id"] == 1

    def test_acquire_success(self):
        """首次获取锁成功"""
        store = self._make_in_memory_store()
        guard = IngestGuard(store)

        result = guard.acquire()
        assert result is True

        # 验证数据库中 is_running 为 1
        row = store.fetch_one("SELECT * FROM ingest_lock WHERE id = 1")
        assert row["is_running"] == 1

    def test_acquire_fail_when_locked(self):
        """已锁定时获取失败"""
        store = self._make_in_memory_store()
        guard = IngestGuard(store)

        # 首次获取成功
        first = guard.acquire()
        assert first is True

        # 再次获取失败
        second = guard.acquire()
        assert second is False

    def test_release_works(self):
        """释放后可再次获取"""
        store = self._make_in_memory_store()
        guard = IngestGuard(store)

        # 获取锁
        guard.acquire()
        row = store.fetch_one("SELECT is_running FROM ingest_lock WHERE id = 1")
        assert row["is_running"] == 1

        # 释放锁
        guard.release()
        row = store.fetch_one("SELECT is_running FROM ingest_lock WHERE id = 1")
        assert row["is_running"] == 0

        # 释放后可再次获取
        reacquire = guard.acquire()
        assert reacquire is True
