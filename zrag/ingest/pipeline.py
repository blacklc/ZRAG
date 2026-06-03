"""文档摄入流程编排器

定义文档摄入流水线中所使用的数据类（ProgressEvent、ErrorEvent、IngestReport）
以及核心编排器 IngestionPipeline。

数据流: Source -> Chunk -> Embed -> SQLite -> ChromaDB -> processed_docs
"""

import logging
from dataclasses import dataclass, field
from typing import Callable

from zrag.embed.base import EmbeddingModel
from zrag.ingest.chunking.base import ChunkingStrategy
from zrag.ingest.sources.base import DocumentSource
from zrag.store.sqlite_store import SQLiteStore
from zrag.store.vector_store import ChromaStore

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    """摄入进度事件

    用于向调用者反馈当前正在处理的文档及其所处阶段。

    @param stage: 处理阶段, 取值 "source" | "chunk" | "embed" | "store"
    @type  stage: str
    @param source_id: 正在处理的文档标识
    @type  source_id: str
    @param status: 阶段状态, 取值 "start" | "done" | "skip"
    @type  status: str
    @param detail: 附加描述信息, defaults to ""
    @type  detail: str, optional
    """
    stage: str
    source_id: str
    status: str
    detail: str = ""


@dataclass
class ErrorEvent:
    """摄入错误事件

    记录单篇文档处理过程中发生的异常信息。

    @param source_id: 出错文档的来源标识
    @type  source_id: str
    @param error: 错误描述字符串
    @type  error: str
    @param exception: 原始异常对象, defaults to None
    @type  exception: Exception | None, optional
    """
    source_id: str
    error: str
    exception: Exception | None = None


@dataclass
class IngestReport:
    """摄入结果报告

    汇总一次 run() 调用的全部处理结果, 包括各类文档计数和错误详情。

    @param total: 从 Source 获取到的文档总数
    @type  total: int, optional
    @param new: 新导入的文档数量
    @type  new: int, optional
    @param updated: 内容更新后重新导入的文档数量
    @type  updated: int, optional
    @param skipped: 因 hash 未变而跳过的文档数量
    @type  skipped: int, optional
    @param failed: 处理失败的文档数量
    @type  failed: int, optional
    @param errors: 失败文档的详细错误列表
    @type  errors: list[ErrorEvent], optional
    """
    total: int = 0
    new: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[ErrorEvent] = field(default_factory=list)


class IngestionPipeline:
    """文档摄入编排器

    编排 Source -> Chunk -> Embed -> SQLite -> ChromaDB -> processed_docs 的完整流程。
    支持增量导入（content_hash 对比）和全量导入。

    所有依赖通过构造方法注入, 便于测试和替换。

    @param sqlite_store: SQLite 持久化存储
    @type  sqlite_store: SQLiteStore
    @param chroma_store: ChromaDB 向量存储
    @type  chroma_store: ChromaStore
    @param embedder: Embedding 模型
    @type  embedder: EmbeddingModel
    @param chunker: 文档分块策略
    @type  chunker: ChunkingStrategy
    @param batch_size: 从 Source 获取文档时的批次大小, defaults to 5
    @type  batch_size: int, optional
    @param on_error: 文档处理失败时的回调函数, 接收 ErrorEvent 参数;
                     若未提供, 则仅记录日志并继续处理下一篇文档
    @type  on_error: callable | None, optional
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        chroma_store: ChromaStore,
        embedder: EmbeddingModel,
        chunker: ChunkingStrategy,
        batch_size: int = 5,
        on_error: Callable | None = None,
    ):
        """构造方法

        @param sqlite_store: SQLite 持久化存储
        @type  sqlite_store: SQLiteStore
        @param chroma_store: ChromaDB 向量存储
        @type  chroma_store: ChromaStore
        @param embedder: Embedding 模型
        @type  embedder: EmbeddingModel
        @param chunker: 文档分块策略
        @type  chunker: ChunkingStrategy
        @param batch_size: 从 Source 获取文档时的批次大小, defaults to 5
        @type  batch_size: int, optional
        @param on_error: 文档处理失败时的回调函数, 接收 ErrorEvent 参数;
                         若未提供, 则仅记录日志并继续处理下一篇文档
        @type  on_error: callable | None, optional
        """
        self.sqlite_store = sqlite_store
        self.chroma_store = chroma_store
        self.embedder = embedder
        self.chunker = chunker
        self.batch_size = batch_size
        self._on_error = on_error

    def run(
        self,
        source: DocumentSource,
        full: bool = False,
        on_progress: Callable | None = None,
    ) -> IngestReport:
        """执行摄入流程

        对 Source 产出的每篇文档执行以下步骤:
          1. 检查 processed_docs（增量模式）
          2. 跳过 hash 未变更的文档
          3. full=True 时忽略缓存, 重新处理所有文档
          4. Chunk -> Embed -> SQLite 事务写入 -> ChromaDB 写入 -> 更新 processed_docs
          5. 每篇文档独立事务

        单篇文档处理失败不会中断后续文档的处理,
        失败信息会记录到 IngestReport 的 errors 列表中。

        @param source: 文档数据源
        @type  source: DocumentSource
        @param full: 是否全量导入（忽略 processed_docs 缓存）, defaults to False
        @type  full: bool, optional
        @param on_progress: 进度回调函数, 接收 ProgressEvent 参数
        @type  on_progress: callable, optional

        @return: 摄入结果报告
        @type:   IngestReport
        """
        all_docs = []
        for batch in source.fetch_batch(batch_size=self.batch_size):
            all_docs.extend(batch)

        report = IngestReport(total=len(all_docs))

        for doc in all_docs:
            # ---- 增量/全量判断 ----
            existing = None
            if not full:
                existing = self.sqlite_store.get_processed(doc.source_id)
                if existing is not None and existing["content_hash"] == doc.content_hash:
                    report.skipped += 1
                    self._emit_progress(on_progress, "source", doc.source_id, "skip")
                    continue

            # 判断文档是全新还是更新
            is_new = full or existing is None

            # ---- 开始处理 ----
            try:
                self._emit_progress(on_progress, "chunk", doc.source_id, "start")
                chunks = self.chunker.chunk(doc)
                self._emit_progress(on_progress, "chunk", doc.source_id, "done")

                self._emit_progress(on_progress, "embed", doc.source_id, "start")
                vectors = self.embedder.embed([c.content for c in chunks])
                self._emit_progress(on_progress, "embed", doc.source_id, "done")

                self._emit_progress(on_progress, "store", doc.source_id, "start")

                # SQLite 事务: 删除旧数据 -> 写入新块 -> 提交
                with self.sqlite_store.transaction():
                    self.sqlite_store.delete_by_source(doc.source_id)
                    self.sqlite_store.add_chunks(chunks)

                # ChromaDB 写入: 删除旧向量 -> 写入新向量
                self.chroma_store.delete_by_source(doc.source_id)
                self.chroma_store.add(
                    ids=[c.chunk_id for c in chunks],
                    embeddings=vectors,
                    metadatas=[
                        {
                            "source_id": c.source_id,
                            "source_type": c.source_type,
                            "doc_title": c.doc_title,
                            "chunk_index": c.chunk_index,
                        }
                        for c in chunks
                    ],
                )
                self._emit_progress(on_progress, "store", doc.source_id, "done")

                # 更新 processed_docs
                self.sqlite_store.upsert_processed(doc)

                if is_new:
                    report.new += 1
                else:
                    report.updated += 1

            except Exception as e:
                logger.exception("文档 %s 处理失败: %s", doc.source_id, str(e))
                report.failed += 1
                error_event = ErrorEvent(
                    source_id=doc.source_id,
                    error=str(e),
                    exception=e,
                )
                report.errors.append(error_event)
                if self._on_error:
                    self._on_error(error_event)

        return report

    @staticmethod
    def _emit_progress(
        on_progress: Callable | None,
        stage: str,
        source_id: str,
        status: str,
        detail: str = "",
    ) -> None:
        """发射进度事件

        @param on_progress: 进度回调函数, 若为 None 则不执行任何操作
        @type  on_progress: callable | None
        @param stage: 处理阶段
        @type  stage: str
        @param source_id: 文档标识
        @type  source_id: str
        @param status: 阶段状态
        @type  status: str
        @param detail: 附加描述信息, defaults to ""
        @type  detail: str, optional
        """
        if on_progress:
            on_progress(ProgressEvent(
                stage=stage,
                source_id=source_id,
                status=status,
                detail=detail,
            ))
