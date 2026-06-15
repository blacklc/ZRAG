"""切片 47 — SQLiteStore ingest_tasks 表测试

测试内容:
  - init_db() 创建 ingest_tasks 表
  - INSERT / SELECT / UPDATE / DELETE CRUD 操作
  - 多条记录共存
  - 默认值验证
"""

import pytest

from zrag.store.sqlite_store import SQLiteStore


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def store():
    """返回基于内存数据库的 SQLiteStore 实例"""
    s = SQLiteStore(db_path=":memory:")
    s.init_db()
    return s


# ============================================================
# Tests
# ============================================================


class TestIngestTasksTable:
    """ingest_tasks 表 CRUD 行为验证"""

    # --------------------------------------------------
    # 1. 建表验证
    # --------------------------------------------------

    def test_init_db_creates_table(self, store):
        """init_db() 后 ingest_tasks 表应存在于 sqlite_master 中"""
        result = store.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ingest_tasks'"
        )
        assert result is not None
        assert result["name"] == "ingest_tasks"

    # --------------------------------------------------
    # 2. INSERT + SELECT
    # --------------------------------------------------

    def test_insert_and_select(self, store):
        """INSERT 一行后 SELECT 回来，所有字段值正确"""
        store.execute(
            "INSERT INTO ingest_tasks (id, task_type, status, total, processed) "
            "VALUES (?, ?, ?, ?, ?)",
            ("task_001", "import", "running", 10, 3),
        )
        row = store.fetch_one("SELECT * FROM ingest_tasks WHERE id = ?", ("task_001",))
        assert row is not None
        assert row["id"] == "task_001"
        assert row["task_type"] == "import"
        assert row["status"] == "running"
        assert row["total"] == 10
        assert row["processed"] == 3

    # --------------------------------------------------
    # 3. UPDATE
    # --------------------------------------------------

    def test_update(self, store):
        """UPDATE status / total / processed 后数值正确"""
        store.execute(
            "INSERT INTO ingest_tasks (id, task_type, status, total, processed) "
            "VALUES (?, ?, ?, ?, ?)",
            ("task_002", "export", "pending", 20, 0),
        )
        store.execute(
            "UPDATE ingest_tasks SET status = ?, total = ?, processed = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            ("completed", 20, 20, "task_002"),
        )
        row = store.fetch_one("SELECT * FROM ingest_tasks WHERE id = ?", ("task_002",))
        assert row is not None
        assert row["status"] == "completed"
        assert row["total"] == 20
        assert row["processed"] == 20

    # --------------------------------------------------
    # 4. DELETE
    # --------------------------------------------------

    def test_delete(self, store):
        """DELETE 后 SELECT 应返回 None"""
        store.execute(
            "INSERT INTO ingest_tasks (id, task_type) VALUES (?, ?)",
            ("task_003", "cleanup"),
        )
        store.execute("DELETE FROM ingest_tasks WHERE id = ?", ("task_003",))
        row = store.fetch_one("SELECT * FROM ingest_tasks WHERE id = ?", ("task_003",))
        assert row is None

    # --------------------------------------------------
    # 5. 多条记录共存
    # --------------------------------------------------

    def test_multiple_tasks_coexist(self, store):
        """INSERT 两条不同 id 的任务，应能同时查询到"""
        store.execute(
            "INSERT INTO ingest_tasks (id, task_type) VALUES (?, ?)",
            ("task_004", "import"),
        )
        store.execute(
            "INSERT INTO ingest_tasks (id, task_type) VALUES (?, ?)",
            ("task_005", "import"),
        )
        rows = store.fetch_all("SELECT id, task_type FROM ingest_tasks ORDER BY id")
        ids = [r["id"] for r in rows]
        assert "task_004" in ids
        assert "task_005" in ids
        assert len(ids) >= 2

    # --------------------------------------------------
    # 6. 默认值验证
    # --------------------------------------------------

    def test_default_values(self, store):
        """仅插入 id 和 task_type 后，status / total / processed 使用默认值"""
        store.execute(
            "INSERT INTO ingest_tasks (id, task_type) VALUES (?, ?)",
            ("task_default", "import"),
        )
        row = store.fetch_one(
            "SELECT id, task_type, status, total, processed FROM ingest_tasks WHERE id = ?",
            ("task_default",),
        )
        assert row is not None
        assert row["status"] == "pending"
        assert row["total"] == 0
        assert row["processed"] == 0
