"""切片 46/48/49 — TaskStatus / IngestTask / TaskManager 单元测试

测试内容:
  - TaskStatus 枚举值定义
  - IngestTask dataclass 字段
  - TaskManager 模块级单例模式
  - create_task 创建任务并写入 manifest 和 DB
  - submit 提交任务到线程池
  - cancel_task 发送取消信号
  - get_task / to_dict 查询与序列化
  - _run 状态流转 (PROCESSING -> DONE / CANCELLED / FAILED)
  - _on_document_done 进度回调
  - _cleanup 清理回调
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from zrag.api.task_manager import IngestTask, TaskManager, TaskStatus


class TestTaskStatus:
    """TaskStatus 枚举值验证"""

    def test_enum_values(self):
        """验证任务状态枚举值定义"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.WAITING_EXPORT.value == "waiting"
        assert TaskStatus.PROCESSING.value == "processing"
        assert TaskStatus.DONE.value == "done"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.FAILED.value == "failed"

    def test_enum_is_str_enum(self):
        """TaskStatus 继承自 str，可通过 .value 获取字符串值"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.WAITING_EXPORT.value == "waiting"
        assert TaskStatus.PROCESSING.value == "processing"
        assert TaskStatus.DONE.value == "done"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.FAILED.value == "failed"


class TestIngestTask:
    """IngestTask dataclass 字段验证"""

    def test_basic_fields(self):
        """基本字段赋值正确"""
        task = IngestTask(
            id="task-1",
            task_type="full",
            status=TaskStatus.PENDING,
        )
        assert task.id == "task-1"
        assert task.task_type == "full"
        assert task.status == TaskStatus.PENDING
        assert task.total == 0
        assert task.processed == 0

    def test_with_all_fields(self):
        """所有字段赋值正确"""
        task = IngestTask(
            id="task-2",
            task_type="incremental",
            status=TaskStatus.PROCESSING,
            total=10,
            processed=3,
            created_at="2026-06-10T10:00:00",
            updated_at="2026-06-10T10:05:00",
        )
        assert task.id == "task-2"
        assert task.task_type == "incremental"
        assert task.status == TaskStatus.PROCESSING
        assert task.total == 10
        assert task.processed == 3
        assert task.created_at == "2026-06-10T10:00:00"
        assert task.updated_at == "2026-06-10T10:05:00"


class TestTaskManagerSingleton:
    """TaskManager 模块级单例模式验证"""

    def test_get_instance_returns_same(self):
        """get_instance() 多次调用返回同一实例"""
        m1 = TaskManager.get_instance()
        m2 = TaskManager.get_instance()
        assert m1 is m2

    def test_instance_has_expected_attrs(self):
        """TaskManager 实例包含预期的属性"""
        manager = TaskManager.get_instance()
        # 注意: 需要先调用 get_instance 初始化
        assert hasattr(manager, "_executor")
        assert hasattr(manager, "_tasks")
        assert hasattr(manager, "_events")


class TestTaskManager:
    """TaskManager 核心功能验证（mock 依赖）"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置 TaskManager._instance 确保测试隔离"""
        TaskManager._instance = None
        yield
        TaskManager._instance = None

    @pytest.fixture
    def manager(self):
        """返回新创建的 TaskManager 实例"""
        mgr = TaskManager()
        mgr._write_manifest = MagicMock()
        mgr._upsert_task_db = MagicMock()
        return mgr

    # --------------------------------------------------
    # 1. create_task
    # --------------------------------------------------

    def test_create_task_creates_with_pending_status(self, manager):
        """create_task 返回 PENDING 状态的任务"""
        task = manager.create_task("full")
        assert task.status == TaskStatus.PENDING
        assert task.task_type == "full"
        assert task.id is not None
        assert len(task.id) > 0

    def test_create_task_incremental(self, manager):
        """create_task 支持增量任务类型"""
        task = manager.create_task("incremental")
        assert task.task_type == "incremental"

    def test_create_task_generates_uuid(self, manager):
        """create_task 生成 UUID 作为任务 ID"""
        task1 = manager.create_task("full")
        task2 = manager.create_task("full")
        assert task1.id != task2.id

    def test_create_task_sets_timestamps(self, manager):
        """create_task 设置 created_at 和 updated_at"""
        task = manager.create_task("full")
        assert task.created_at != ""
        assert task.updated_at == task.created_at

    def test_create_task_stores_in_tasks_dict(self, manager):
        """create_task 将任务保存到 _tasks 字典"""
        task = manager.create_task("full")
        assert manager._tasks[task.id] is task

    def test_create_task_creates_event(self, manager):
        """create_task 创建 threading.Event"""
        task = manager.create_task("full")
        assert task.id in manager._events
        from threading import Event
        assert isinstance(manager._events[task.id], Event)

    def test_create_task_writes_manifest(self, manager):
        """create_task 调用 _write_manifest"""
        manager._write_manifest = MagicMock()
        task = manager.create_task("full")
        manager._write_manifest.assert_called_once_with(task)

    def test_create_task_upserts_db(self, manager):
        """create_task 调用 _upsert_task_db"""
        manager._upsert_task_db = MagicMock()
        task = manager.create_task("full")
        manager._upsert_task_db.assert_called_once_with(task)

    # --------------------------------------------------
    # 2. submit
    # --------------------------------------------------

    def test_submit_updates_status(self, manager):
        """submit 将任务状态改为 WAITING_EXPORT"""
        task = manager.create_task("full")
        pipeline = MagicMock()
        source = MagicMock()
        # 阻止 executor 实际执行 _run (否则后台线程瞬间完成,状态变为 DONE)
        with patch.object(manager._executor, "submit") as mock_submit:
            manager.submit(task, pipeline, source, full=False)
        assert task.status == TaskStatus.WAITING_EXPORT

    def test_submit_submits_to_executor(self, manager):
        """submit 提交到线程池"""
        with patch.object(manager._executor, "submit") as mock_submit:
            task = manager.create_task("full")
            pipeline = MagicMock()
            source = MagicMock()
            manager.submit(task, pipeline, source, full=True)
            mock_submit.assert_called_once()
            args, _ = mock_submit.call_args
            assert args[0] == manager._run

    # --------------------------------------------------
    # 3. cancel_task
    # --------------------------------------------------

    def test_cancel_task_changes_status(self, manager):
        """cancel_task 将任务状态设为 CANCELLED"""
        task = manager.create_task("full")
        manager.cancel_task(task.id)
        assert task.status == TaskStatus.CANCELLED

    def test_cancel_task_sets_event(self, manager):
        """cancel_task 设置 threading.Event"""
        task = manager.create_task("full")
        event = manager._events[task.id]
        assert not event.is_set()
        manager.cancel_task(task.id)
        assert event.is_set()

    def test_cancel_task_nonexistent(self, manager):
        """取消不存在的任务不会报错"""
        manager.cancel_task("nonexistent-id")  # should not raise

    # --------------------------------------------------
    # 4. get_task
    # --------------------------------------------------

    def test_get_task_returns_task(self, manager):
        """get_task 返回已创建的任务"""
        task = manager.create_task("full")
        retrieved = manager.get_task(task.id)
        assert retrieved is task

    def test_get_task_returns_none(self, manager):
        """get_task 对于不存在的 ID 返回 None"""
        retrieved = manager.get_task("nonexistent-id")
        assert retrieved is None

    # --------------------------------------------------
    # 5. to_dict
    # --------------------------------------------------

    def test_to_dict_serialization(self, manager):
        """to_dict 返回正确的字典格式"""
        task = manager.create_task("incremental")
        task.total = 15
        task.processed = 7
        d = manager.to_dict(task)
        assert d["task_id"] == task.id
        assert d["task_type"] == "incremental"
        assert d["status"] == "pending"
        assert d["total"] == 15
        assert d["processed"] == 7
        assert d["created_at"] == task.created_at
        assert d["updated_at"] == task.updated_at

    def test_to_dict_status_uses_value(self, manager):
        """to_dict 使用 TaskStatus 的 value（字符串）"""
        task = manager.create_task("full")
        task.status = TaskStatus.DONE
        d = manager.to_dict(task)
        assert d["status"] == "done"

    # --------------------------------------------------
    # 6. _run — 状态流转
    # --------------------------------------------------

    def test_run_successful(self, manager):
        """_run 成功执行后状态变为 DONE"""
        task = manager.create_task("full")
        pipeline = MagicMock()
        source = MagicMock()

        manager._run(task, pipeline, source, full=False)

        assert task.status == TaskStatus.DONE
        pipeline.run.assert_called_once()

    def test_run_calls_pipeline_with_callbacks(self, manager):
        """_run 传递 should_cancel 和 on_document_done 到 pipeline.run"""
        task = manager.create_task("full")
        task.total = 3
        pipeline = MagicMock()
        source = MagicMock()

        manager._run(task, pipeline, source, full=True)

        _, kwargs = pipeline.run.call_args
        assert kwargs["full"] is True
        assert callable(kwargs["should_cancel"])
        assert callable(kwargs["on_document_done"])

    def test_run_cancelled(self, manager):
        """_run 中 pipeline 抛出异常且 cancel event 已设置 -> CANCELLED"""
        task = manager.create_task("full")
        pipeline = MagicMock()
        source = MagicMock()
        pipeline.run.side_effect = Exception("中断")
        manager._events[task.id].set()  # 模拟取消信号

        manager._run(task, pipeline, source, full=False)

        assert task.status == TaskStatus.CANCELLED

    def test_run_failed(self, manager):
        """_run 中 pipeline 抛出异常且未取消 -> FAILED"""
        task = manager.create_task("full")
        pipeline = MagicMock()
        source = MagicMock()
        pipeline.run.side_effect = Exception("未知错误")

        manager._run(task, pipeline, source, full=False)

        assert task.status == TaskStatus.FAILED

    def test_run_updates_updated_at(self, manager):
        """_run 结束后更新 updated_at"""
        task = manager.create_task("full")
        pipeline = MagicMock()
        source = MagicMock()
        original = task.updated_at

        manager._run(task, pipeline, source, full=False)

        assert task.updated_at != original

    def test_run_upserts_db_in_finally(self, manager):
        """_run 在 finally 中更新数据库"""
        task = manager.create_task("full")
        pipeline = MagicMock()
        source = MagicMock()
        manager._upsert_task_db = MagicMock()

        manager._run(task, pipeline, source, full=False)

        manager._upsert_task_db.assert_called_with(task)

    # --------------------------------------------------
    # 7. _on_document_done
    # --------------------------------------------------

    def test_on_document_done_increments_processed(self, manager):
        """_on_document_done 递增 processed 计数"""
        task = manager.create_task("full")
        task.processed = 0

        manager._on_document_done(task)
        assert task.processed == 1

        manager._on_document_done(task)
        assert task.processed == 2

    def test_on_document_done_updates_updated_at(self, manager):
        """_on_document_done 更新 updated_at"""
        task = manager.create_task("full")
        original = task.updated_at

        manager._on_document_done(task)

        assert task.updated_at != original

    def test_on_document_done_upserts_db(self, manager):
        """_on_document_done 更新数据库记录"""
        task = manager.create_task("full")
        manager._upsert_task_db = MagicMock()

        manager._on_document_done(task)

        manager._upsert_task_db.assert_called_once_with(task)

    # --------------------------------------------------
    # 8. _cleanup
    # --------------------------------------------------

    def test_cleanup_submits_to_executor(self, manager):
        """_cleanup 向线程池提交清理任务"""
        task = manager.create_task("full")
        with patch.object(manager._executor, "submit") as mock_submit:
            manager._cleanup(task)
            mock_submit.assert_called_once()
            args, _ = mock_submit.call_args
            assert args[0] == TaskManager._do_cleanup

    # --------------------------------------------------
    # 9. _write_manifest
    # --------------------------------------------------

    def test_write_manifest_creates_json(self):
        """_write_manifest 写入格式正确的 manifest.json"""
        TaskManager._instance = None
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(settings, 'BASE_DIR', tmpdir):
                from zrag.store.sqlite_store import SQLiteStore
                store = SQLiteStore(db_path=f"{tmpdir}/test.db")
                store.init_db()

                manager = TaskManager()
                manager._upsert_task_db = MagicMock()
                task = manager.create_task("full")

                export_dir = os.path.join(tmpdir, "data", "export", task.id)
                manifest_path = os.path.join(export_dir, "manifest.json")
                assert os.path.exists(manifest_path)

                with open(manifest_path) as f:
                    manifest = json.load(f)
                assert manifest["task_id"] == task.id
                assert manifest["source_type"] == "mac_notes"
                assert isinstance(manifest["processed_docs"], list)

    # --------------------------------------------------
    # 10. _upsert_task_db
    # --------------------------------------------------

    def test_upsert_task_db_sql(self):
        """_upsert_task_db 的 SQL INSERT/UPDATE 语法正确"""
        from zrag.store.sqlite_store import SQLiteStore

        store = SQLiteStore(db_path=":memory:")
        store.init_db()

        task = IngestTask(
            id="test-id-1",
            task_type="incremental",
            status=TaskStatus.PENDING,
        )

        # 验证 INSERT
        store.execute(
            "INSERT OR REPLACE INTO ingest_tasks "
            "(id, task_type, status, total, processed, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task.id, task.task_type, task.status.value,
             task.total, task.processed,
             task.created_at, task.updated_at),
        )
        row = store.fetch_one(
            "SELECT * FROM ingest_tasks WHERE id = ?", (task.id,)
        )
        assert row is not None
        assert row["task_type"] == "incremental"
        assert row["status"] == "pending"

        # 验证 UPDATE
        task.status = TaskStatus.PROCESSING
        task.processed = 3
        store.execute(
            "INSERT OR REPLACE INTO ingest_tasks "
            "(id, task_type, status, total, processed, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task.id, task.task_type, task.status.value,
             task.total, task.processed,
             task.created_at, task.updated_at),
        )
        row2 = store.fetch_one(
            "SELECT * FROM ingest_tasks WHERE id = ?", (task.id,)
        )
        assert row2["status"] == "processing"
        assert row2["processed"] == 3

    # --------------------------------------------------
    # 11. _do_cleanup
    # --------------------------------------------------

    def test_do_cleanup_removes_directory(self):
        """_do_cleanup 删除导出目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            TaskManager._do_cleanup(tmpdir)
            assert not os.path.exists(tmpdir)

    def test_do_cleanup_nonexistent(self):
        """_do_cleanup 对不存在的目录不做操作"""
        TaskManager._do_cleanup("/nonexistent/path")  # should not raise

    # --------------------------------------------------
    # 12. should_cancel callback
    # --------------------------------------------------

    def test_should_cancel_returns_false_when_not_set(self, manager):
        """should_cancel 回调在未设置取消时返回 False"""
        task = manager.create_task("full")
        should_cancel = lambda: manager._events[task.id].is_set()
        assert should_cancel() is False

    def test_should_cancel_returns_true_when_set(self, manager):
        """should_cancel 回调在设置取消后返回 True"""
        task = manager.create_task("full")
        should_cancel = lambda: manager._events[task.id].is_set()
        manager.cancel_task(task.id)
        assert should_cancel() is True
