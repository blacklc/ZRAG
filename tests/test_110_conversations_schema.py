"""切片 110 — conversations 表 schema 扩展测试

测试内容:
  - init_db() 后 conversations 表包含 summary 和 summary_updated_at 列
  - 旧表 (无 summary 列) 在 init_db() 时自动迁移，补全列
  - 迁移幂等: init_db() 重复调用不报错
  - INSERT 时可以写入 summary 值，未指定时使用默认值 ''
"""

import pytest

from zrag.store.sqlite_store import SQLiteStore


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def store():
    """返回基于内存数据库的 SQLiteStore 实例，已建表"""
    s = SQLiteStore(db_path=":memory:")
    s.init_db()
    return s


def get_columns(store: SQLiteStore, table: str) -> list[str]:
    """获取指定表的所有列名"""
    rows = store.fetch_all(f"PRAGMA table_info({table})")
    return [r["name"] for r in rows]


# ============================================================
# Tests
# ============================================================


class TestConversationsSchema:
    """conversations 表 schema 行为验证"""

    # --------------------------------------------------
    # 1. 新数据库包含新列
    # --------------------------------------------------

    def test_new_db_has_summary_column(self, store):
        """init_db() 后 conversations 表应包含 summary 列"""
        columns = get_columns(store, "conversations")
        assert "summary" in columns

    def test_new_db_has_summary_updated_at_column(self, store):
        """init_db() 后 conversations 表应包含 summary_updated_at 列"""
        columns = get_columns(store, "conversations")
        assert "summary_updated_at" in columns

    # --------------------------------------------------
    # 2. 旧数据库迁移后补全新列
    # --------------------------------------------------

    def test_old_db_migration_adds_summary(self):
        """旧表（无 summary 列）在 init_db() 后自动补全"""
        s = SQLiteStore(db_path=":memory:")
        # 模拟旧 schema：先手动建表，不包含 summary 和 summary_updated_at
        conn = s._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # 验证旧表没有新列
        columns_before = get_columns(s, "conversations")
        assert "summary" not in columns_before
        assert "summary_updated_at" not in columns_before

        # 执行 init_db() 触发迁移
        s.init_db()
        columns_after = get_columns(s, "conversations")
        assert "summary" in columns_after
        assert "summary_updated_at" in columns_after

    # --------------------------------------------------
    # 3. 迁移幂等性
    # --------------------------------------------------

    def test_migration_idempotent(self, store):
        """重复调用 init_db() 不应报错，列保持不变"""
        store.init_db()  # 第二次调用
        columns = get_columns(store, "conversations")
        assert "summary" in columns
        assert "summary_updated_at" in columns

    def test_migration_idempotent_old_db(self):
        """旧表迁移后再次 init_db() 不应报错"""
        s = SQLiteStore(db_path=":memory:")
        conn = s._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # 第一次迁移
        s.init_db()
        columns_first = get_columns(s, "conversations")
        assert "summary" in columns_first
        assert "summary_updated_at" in columns_first

        # 第二次重复调用
        s.init_db()
        columns_second = get_columns(s, "conversations")
        assert columns_first == columns_second

    # --------------------------------------------------
    # 4. INSERT with summary
    # --------------------------------------------------

    def test_insert_with_summary(self, store):
        """INSERT 时指定 summary 值，SELECT 应原样返回"""
        store.execute(
            "INSERT INTO conversations (id, title, summary) VALUES (?, ?, ?)",
            ("conv_001", "Test Conversation", "This is a summary"),
        )
        row = store.fetch_one(
            "SELECT id, title, summary FROM conversations WHERE id = ?",
            ("conv_001",),
        )
        assert row is not None
        assert row["summary"] == "This is a summary"

    def test_insert_without_summary_uses_default(self, store):
        """INSERT 时不指定 summary，应使用默认值 ''"""
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            ("conv_002", "No Summary"),
        )
        row = store.fetch_one(
            "SELECT id, title, summary, summary_updated_at FROM conversations WHERE id = ?",
            ("conv_002",),
        )
        assert row is not None
        assert row["summary"] == ""
        assert row["summary_updated_at"] == ""
