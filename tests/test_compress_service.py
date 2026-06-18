"""切片 #116 — CompressService 异步压缩调度 单元测试

测试 CompressService 的异步压缩功能，包括:
- 提交压缩任务后摘要被正确写入数据库
- 压缩 LLM 调用失败时静默降级，不向调用方抛异常
- 对同一会话快速连续提交多条压缩任务时不出现竞态崩溃
"""

import os
import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import django.conf
import pytest

from zrag.utils.compress import CompressService


class TestCompressService:
    """CompressService 异步压缩服务单元测试"""

    CONVERSATIONS_DDL = """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            summary_updated_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """

    @pytest.fixture
    def temp_db(self):
        """创建临时 SQLite 数据库文件并初始化 conversations 表

        测试结束后自动清理临时文件。

        @yield: 临时数据库文件路径
        @rtype: str
        """
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute(self.CONVERSATIONS_DDL)
        conn.close()
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def executor(self):
        """创建 ThreadPoolExecutor 实例用于测试

        @yield: ThreadPoolExecutor
        @rtype: ThreadPoolExecutor
        """
        pool = ThreadPoolExecutor(max_workers=2)
        yield pool
        pool.shutdown(wait=True)

    @staticmethod
    def _insert_conversation(db_path, conv_id, title="测试会话"):
        """向测试数据库中插入一条会话记录

        @param db_path: 数据库文件路径
        @type  db_path: str
        @param conv_id: 会话 ID
        @type  conv_id: str
        @param title:   会话标题, defaults to "测试会话"
        @type  title:   str, optional
        """
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            (conv_id, title),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _read_summary(db_path, conv_id):
        """从指定数据库读取会话的 summary 字段

        @param db_path: 数据库文件路径
        @type  db_path: str
        @param conv_id: 会话 ID
        @type  conv_id: str

        @return: summary 字段值，若记录不存在则返回 None
        @rtype:  str | None
        """
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT summary FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    # ======================== 测试用例 ========================

    def test_submit_triggers_compression(self, temp_db, executor):
        """验证 submit 提交压缩任务后，数据库中的 summary 字段被正确写入

        1. 创建临时 SQLite 数据库，插入一条会话记录
        2. mock ConversationSummarizer.summarize() 返回固定摘要
        3. 通过 patch 将 ZRAG_STORAGE 指向临时数据库
        4. 调用 submit 后 sleep 等待异步任务完成
        5. 验证数据库中 summary 字段的值与 mock 返回值一致
        """
        self._insert_conversation(temp_db, "conv-1")

        service = CompressService(executor=executor, llm_provider=MagicMock())
        service._summarizer.summarize = MagicMock(
            return_value="这是压缩后的测试摘要"
        )

        with patch.object(
            django.conf.settings,
            "ZRAG_STORAGE",
            {"sqlite_path": temp_db},
        ):
            service.submit("conv-1", "旧摘要", "用户提问", "助手回复")
            time.sleep(0.5)

        actual = self._read_summary(temp_db, "conv-1")
        assert actual == "这是压缩后的测试摘要"

    def test_compression_failure_silent(self, temp_db, executor):
        """验证 ConversationSummarizer 抛出异常时，不向调用方抛异常

        并且数据库中原始 summary 保持不变（空字符串）。

        1. 创建临时 SQLite 数据库，插入一条会话记录
        2. mock ConversationSummarizer.summarize() 抛出 RuntimeError
        3. 调用 submit（应静默捕获异常，不抛出）
        4. sleep 等待异步任务完成
        5. 验证数据库中 summary 仍为默认空字符串
        """
        self._insert_conversation(temp_db, "conv-2")

        service = CompressService(executor=executor, llm_provider=MagicMock())
        service._summarizer.summarize = MagicMock(
            side_effect=RuntimeError("LLM 调用失败")
        )

        with patch.object(
            django.conf.settings,
            "ZRAG_STORAGE",
            {"sqlite_path": temp_db},
        ):
            # submit 方法本身不应抛出异常
            service.submit("conv-2", "", "用户查询", "助手回复")
            time.sleep(0.5)

        actual = self._read_summary(temp_db, "conv-2")
        assert actual is not None
        assert actual == ""

    def test_concurrent_submissions(self, temp_db, executor):
        """验证对同一会话快速连续提交 3 次压缩任务时，不出现竞态崩溃

        1. 创建临时 SQLite 数据库，插入一条会话记录
        2. mock ConversationSummarizer 返回固定摘要
        3. 快速连续调用 submit 3 次（不同用户查询和回复）
        4. sleep 等待所有异步任务完成
        5. 验证至少有一条摘要被写入（不依赖最终写入顺序）
        """
        self._insert_conversation(temp_db, "conv-3")

        service = CompressService(executor=executor, llm_provider=MagicMock())
        # 每次调用均返回相同摘要，避免并发写时序导致的非确定性断言
        service._summarizer.summarize = MagicMock(
            return_value="并发压缩摘要"
        )

        with patch.object(
            django.conf.settings,
            "ZRAG_STORAGE",
            {"sqlite_path": temp_db},
        ):
            for i in range(3):
                service.submit(
                    "conv-3",
                    f"旧摘要{i}",
                    f"用户提问{i}",
                    f"助手回复{i}",
                )
            time.sleep(1.0)  # 等待所有异步任务完成

        actual = self._read_summary(temp_db, "conv-3")
        assert actual is not None
        # 至少有一条压缩摘要被成功写入
        assert actual != ""
