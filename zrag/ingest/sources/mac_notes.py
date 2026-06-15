"""macOS 备忘录数据源实现 — 文件桥接模式

通过轮询宿主机导出脚本输出的 result.json 文件，
读取其中已导出笔记的 JSON 文件并构造 RawDocument。
不再直接调用 AppleScript（容器内无法执行 osascript）。
"""

import json
import logging
import time
from pathlib import Path
from typing import Callable, Iterator, Optional

from zrag.ingest.sources.base import DocumentSource
from zrag.models.document import RawDocument

logger = logging.getLogger(__name__)


class MacNotesSource(DocumentSource):
    """macOS 备忘录数据源 — 文件桥接模式

    在容器化部署环境下，宿主机导出脚本将 macOS Notes 导出为 JSON 文件,
    MacNotesSource 轮询等待导出完成后读取这些文件。

    @param export_dir: 导出文件目录，默认为 data/pro/export/<task_id>
    @type  export_dir: str, optional
    @param poll_interval: 轮询间隔秒数，defaults to 2
    @type  poll_interval: int, optional
    """

    def __init__(
        self,
        export_dir: str | None = None,
        poll_interval: int = 2,
        should_cancel: Optional[Callable] = None,
    ):
        """构造方法

        @param export_dir: 导出文件目录，未指定时在 fetch_batch 中设置
        @type  export_dir: str, optional
        @param poll_interval: 轮询间隔秒数，defaults to 2
        @type  poll_interval: int, optional
        @param should_cancel: 取消检查回调，返回 True 时中断轮询等待，defaults to None
        @type  should_cancel: callable | None, optional
        """
        self._export_dir = export_dir
        self._poll_interval = poll_interval
        self._total = 0
        self.should_cancel = should_cancel

    def fetch_batch(self, batch_size: int = 1) -> Iterator[list[RawDocument]]:
        """分批获取已导出的笔记

        阶段 1: 轮询等待 result.json 文件就绪
        阶段 2: 读取所有 <note_id>.json 文件，逐篇 yield

        @param batch_size: 每批次最大文档数量, defaults to 1
        @type  batch_size: int, optional

        @return: 生成器，每次 yield 一个 RawDocument 列表
        @rtype:   Iterator[list[RawDocument]]

        @raises FileNotFoundError: 导出目录不存在时抛出
        @raises ValueError: result.json 格式异常时抛出
        """
        if self._export_dir is None:
            raise ValueError("export_dir 未设置")

        export_path = Path(self._export_dir)
        result_file = export_path / "result.json"

        # 阶段 1: 轮询等待 result.json（可被 should_cancel 中断）
        logger.info("等待 result.json 就绪: %s (轮询间隔: %ds)",
                    result_file, self._poll_interval)
        while not result_file.exists():
            if self.should_cancel and self.should_cancel():
                raise RuntimeError("任务已被取消，轮询等待中断")
            time.sleep(self._poll_interval)
        logger.info("result.json 已就绪")

        try:
            with open(result_file, encoding="utf-8") as f:
                result = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.exception("读取 result.json 失败: %s", result_file)
            raise ValueError(f"result.json 格式异常或读取失败: {e}") from e

        if result.get("status") != "ok":
            raise ValueError(
                f"导出未正常完成，status={result.get('status')}"
            )

        self._total = result.get("success", 0)
        logger.info("导出完成: success=%d expected=%d",
                    result.get("success", 0), result.get("expected", 0))

        # 阶段 2: 逐篇读取笔记 JSON 文件
        json_files = sorted(export_path.glob("*.json"))
        batch: list[RawDocument] = []
        for filepath in json_files:
            if filepath.name in ("manifest.json", "result.json"):
                continue

            try:
                with open(filepath, encoding="utf-8") as f:
                    note = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("跳过损坏的笔记文件: %s — %s", filepath, e)
                continue

            doc = RawDocument(
                source_id=note["source_id"],
                source_type=note["source_type"],
                content=note["content"],
                content_hash=note["content_hash"],
                metadata=note.get("metadata", {}),
            )
            batch.append(doc)

            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:
            yield batch

    @property
    def source_type(self) -> str:
        """获取数据源类型标识

        @return: 数据源类型字符串 "mac_notes"
        @type:   str
        """
        return "mac_notes"

    @property
    def total_count(self) -> int:
        """获取本次摄取的文档总数

        @return: result.json 中记录的 success 值
        @type:   int
        """
        return self._total
