"""摄入任务管理器

定义摄入任务的状态枚举、数据类以及 TaskManager 模块级单例。
"""

import json
import logging
import os
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """摄入任务状态枚举

    PENDING — 已创建任务，等待用户执行导出脚本
    WAITING_EXPORT — 容器侧轮询等待 result.json
    PROCESSING — result.json 就绪，Pipeline 处理中
    DONE — 全部完成
    CANCELLED — 用户手动取消（终态）
    FAILED — 异常终止（终态）
    """
    PENDING = "pending"
    WAITING_EXPORT = "waiting"
    PROCESSING = "processing"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class IngestTask:
    """摄入任务数据类

    字段与 ingest_tasks 数据库表一一对应。
    """
    id: str
    task_type: str
    status: TaskStatus
    total: int = 0
    processed: int = 0
    created_at: str = ""
    updated_at: str = ""


class TaskManager:
    """摄入任务管理器（模块级单例）

    负责创建、提交、取消和查询摄入任务。
    线程池由 settings.ZRAG_INGEST_EXECUTOR 注入。
    取消机制通过 threading.Event 实现。
    """

    _instance = None

    @classmethod
    def get_instance(cls) -> "TaskManager":
        """获取模块级单例实例

        @return: TaskManager 全局唯一实例
        @rtype:  TaskManager
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """构造方法

        获取 Django settings 中的线程池配置，
        初始化任务字典和取消事件字典。
        """
        from django.conf import settings
        self._executor: ThreadPoolExecutor = settings.ZRAG_INGEST_EXECUTOR
        self._tasks: dict[str, IngestTask] = {}
        self._events: dict[str, threading.Event] = {}

    def create_task(self, task_type: str) -> IngestTask:
        """创建摄入任务并持久化

        生成 UUID 作为任务 ID，写入 manifest.json 和 DB。

        @param task_type: 任务类型, 'full' | 'incremental'
        @type  task_type: str

        @return: 新创建的 IngestTask 实例
        @rtype:  IngestTask
        """
        now = datetime.now(timezone.utc).isoformat()
        task = IngestTask(
            id=str(uuid.uuid4()),
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._write_manifest(task)
        self._upsert_task_db(task)
        self._tasks[task.id] = task
        self._events[task.id] = threading.Event()
        logger.info("[task=%s] 任务已创建 task_type=%s status=%s",
                    task.id, task_type, TaskStatus.PENDING.value)
        return task

    def submit(self, task: IngestTask, pipeline, source, full: bool) -> None:
        """提交任务到线程池执行

        将任务状态更新为 WAITING_EXPORT 后提交到后台线程池。

        @param task: 待执行的摄入任务
        @type  task: IngestTask
        @param pipeline: 摄入流程编排器实例
        @param source: 文档数据源实例
        @param full: 是否全量导入
        @type  full: bool
        """
        task.status = TaskStatus.WAITING_EXPORT
        self._executor.submit(self._run, task, pipeline, source, full)
        logger.info("[task=%s] 任务已提交 task_type=%s full=%s",
                    task.id, task.task_type, full)

    def cancel_task(self, task_id: str) -> None:
        """取消指定任务

        通过 threading.Event 发送取消信号。

        @param task_id: 任务 ID
        @type  task_id: str
        """
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            self._events[task_id].set()
            logger.info("[task=%s] 任务已取消", task_id)
        else:
            logger.warning("[task=%s] 取消失败: 任务不存在", task_id)

    def get_task(self, task_id: str) -> IngestTask | None:
        """根据任务 ID 查询任务

        @param task_id: 任务 ID
        @type  task_id: str

        @return: IngestTask 实例，不存在则返回 None
        @rtype:  IngestTask | None
        """
        return self._tasks.get(task_id)

    def to_dict(self, task: IngestTask) -> dict:
        """将 IngestTask 序列化为字典

        @param task: 摄入任务
        @type  task: IngestTask

        @return: 序列化后的字典
        @rtype:  dict
        """
        return {
            "task_id": task.id,
            "task_type": task.task_type,
            "status": task.status.value,
            "total": task.total,
            "processed": task.processed,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    def _write_manifest(self, task: IngestTask) -> None:
        """写入 manifest.json

        创建任务导出目录并写入 manifest.json，
        包含 task_id、source_type 和 processed_docs。

        @param task: 摄入任务
        @type  task: IngestTask
        """
        from django.conf import settings
        from zrag.store.sqlite_store import SQLiteStore

        base_dir = settings.BASE_DIR
        export_dir = os.path.join(base_dir, "data", "export", task.id)
        os.makedirs(export_dir, exist_ok=True)

        store = SQLiteStore()
        rows = store.fetch_all(
            "SELECT source_id, content_hash FROM processed_docs ORDER BY source_id"
        )
        processed_docs = [
            {"source_id": r["source_id"], "content_hash": r["content_hash"]}
            for r in rows
        ]

        manifest = {
            "task_id": task.id,
            "source_type": "mac_notes",
            "processed_docs": processed_docs,
            "created_at": task.created_at,
        }

        manifest_path = os.path.join(export_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        logger.info("[task=%s] manifest.json 已写入, processed_docs=%d",
                    task.id, len(processed_docs))

    def _upsert_task_db(self, task: IngestTask) -> None:
        """将任务写入或更新数据库

        @param task: 摄入任务
        @type  task: IngestTask
        """
        from zrag.store.sqlite_store import SQLiteStore

        try:
            store = SQLiteStore()
            store.execute(
                "INSERT OR REPLACE INTO ingest_tasks "
                "(id, task_type, status, total, processed, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task.id, task.task_type, task.status.value,
                 task.total, task.processed,
                 task.created_at, task.updated_at),
            )
        except Exception:
            logger.exception("[task=%s] 更新任务数据库记录失败", task.id)

    def _run(self, task: IngestTask, pipeline, source, full: bool) -> None:
        """在线程池中执行摄入流程

        @param task: 摄入任务
        @type  task: IngestTask
        @param pipeline: 摄入流程编排器
        @param source: 文档数据源
        @param full: 是否全量导入
        @type  full: bool
        """
        try:
            task.status = TaskStatus.PROCESSING
            logger.info("[task=%s] 摄入处理开始 task_type=%s full=%s",
                        task.id, task.task_type, full)
            pipeline.run(
                source=source,
                full=full,
                on_document_done=lambda: self._on_document_done(task),
                should_cancel=lambda: self._events[task.id].is_set(),
                on_total_known=lambda n: self._on_total_known(task, n),
            )
            task.status = TaskStatus.DONE
            logger.info("[task=%s] 摄入处理完成 total=%d processed=%d",
                        task.id, task.total, task.processed)
        except Exception:
            if self._events[task.id].is_set():
                task.status = TaskStatus.CANCELLED
                logger.warning("[task=%s] 摄入已取消", task.id)
            else:
                task.status = TaskStatus.FAILED
                logger.exception("[task=%s] 摄入处理失败", task.id)
        finally:
            task.updated_at = datetime.now(timezone.utc).isoformat()
            self._upsert_task_db(task)
            self._cleanup(task)

    def _on_document_done(self, task: IngestTask) -> None:
        """文档处理完成后的回调

        增加 processed 计数并更新数据库。

        @param task: 摄入任务
        @type  task: IngestTask
        """
        task.processed += 1
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self._upsert_task_db(task)

    def _on_total_known(self, task: IngestTask, total: int) -> None:
        """fetch_batch 完成后回写文档总数

        @param task: 摄入任务实例
        @type  task: IngestTask
        @param total: 文档总数
        @type  total: int
        """
        task.total = total
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self._upsert_task_db(task)

    def _cleanup(self, task: IngestTask) -> None:
        """提交清理任务到线程池

        不阻塞 Pipeline 线程，清理失败仅记录日志。

        @param task: 摄入任务
        @type  task: IngestTask
        """
        from django.conf import settings
        export_dir = os.path.join(
            settings.BASE_DIR, "data", "export", task.id
        )
        self._executor.submit(self._do_cleanup, export_dir)

    @staticmethod
    def _do_cleanup(export_dir: str) -> None:
        """清理导出目录

        @param export_dir: 导出目录路径
        @type  export_dir: str
        """
        try:
            if os.path.exists(export_dir):
                shutil.rmtree(export_dir)
                logger.info("导出目录已清理: %s", export_dir)
        except Exception:
            logger.exception("清理导出目录失败: %s", export_dir)
