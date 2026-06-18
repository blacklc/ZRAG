"""文档摄入流程编排器

定义文档摄入流水线中所使用的数据类（ErrorEvent、IngestReport）
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
        batch_size: int | None = None,
        on_error: Callable | None = None,
    ):
        """构造方法

        若 batch_size 未显式传入，则从 Django settings.ZRAG_INGEST 配置中读取。
        配置中也未提供时默认使用 5。

        @param sqlite_store: SQLite 持久化存储
        @type  sqlite_store: SQLiteStore
        @param chroma_store: ChromaDB 向量存储
        @type  chroma_store: ChromaStore
        @param embedder: Embedding 模型
        @type  embedder: EmbeddingModel
        @param chunker: 文档分块策略
        @type  chunker: ChunkingStrategy
        @param batch_size: 从 Source 获取文档时的批次大小, defaults to None
                           未传入则从配置 ingest.batch_size 读取
        @type  batch_size: int, optional
        @param on_error: 文档处理失败时的回调函数, 接收 ErrorEvent 参数;
                         若未提供, 则仅记录日志并继续处理下一篇文档
        @type  on_error: callable | None, optional
        """
        self.sqlite_store = sqlite_store
        self.chroma_store = chroma_store
        self.embedder = embedder
        self.chunker = chunker
        if not isinstance(embedder, EmbeddingModel):
            raise TypeError(
                f"embedder 必须是 EmbeddingModel 的子类，实际类型: {type(embedder).__name__}"
            )
        if not isinstance(chunker, ChunkingStrategy):
            raise TypeError(
                f"chunker 必须是 ChunkingStrategy 的子类，实际类型: {type(chunker).__name__}"
            )
        if batch_size is not None:
            self.batch_size = batch_size
        else:
            from django.conf import settings
            ingest_cfg = getattr(settings, "ZRAG_INGEST", {})
            self.batch_size = ingest_cfg.get("batch_size", 5)
        self._on_error = on_error

    def run(
        self,
        source: DocumentSource,
        full: bool = False,
        on_document_done: Callable | None = None,
        should_cancel: Callable | None = None,
        on_total_known: Callable[[int], None] | None = None,
    ) -> IngestReport:
        """执行摄入流程

        对 Source 产出的每篇文档执行以下步骤:
          1. 取消检查（每篇文档开始前检测）
          2. 检查 processed_docs（增量模式）
          3. 跳过 hash 未变更的文档
          4. full=True 时忽略缓存, 重新处理所有文档
          5. Chunk -> Embed -> SQLite 事务写入 -> ChromaDB 写入 -> 更新 processed_docs
          6. 每篇文档独立事务

        单篇文档处理失败不会中断后续文档的处理,
        失败信息会记录到 IngestReport 的 errors 列表中。

        @param source: 文档数据源
        @type  source: DocumentSource
        @param full: 是否全量导入（忽略 processed_docs 缓存）, defaults to False
        @type  full: bool, optional
        @param on_document_done: 每篇文档处理完成后的回调（不论成败）
        @type  on_document_done: callable, optional
        @param should_cancel: 取消检查回调, 返回 True 时中断后续处理
        @type  should_cancel: callable, optional
        @param on_total_known: fetch_batch 完成后通知文档总数的回调
        @type  on_total_known: callable, optional

        @return: 摄入结果报告
        @type:   IngestReport
        """
        if not isinstance(source, DocumentSource):
            raise TypeError(
                f"source 必须是 DocumentSource 的子类，实际类型: {type(source).__name__}"
            )
        logger.info("Pipeline 开始执行", extra={"batch_size": self.batch_size, "full": full})
        # 将取消回调注入 Source，使轮询等待可被中断
        if should_cancel and hasattr(source, 'should_cancel'):
            source.should_cancel = should_cancel
        all_docs = []
        for batch in source.fetch_batch(batch_size=self.batch_size):
            all_docs.extend(batch)

        report = IngestReport(total=len(all_docs))

        if on_total_known:
            on_total_known(len(all_docs))

        for doc in all_docs:
            # ---- 取消检查 ----
            if should_cancel and should_cancel():
                logger.info("摄入任务已被取消，中断后续处理")
                break

            # ---- 增量/全量判断 ----
            existing = None
            if not full:
                existing = self.sqlite_store.get_processed(doc.source_id)
                if existing is not None and existing["content_hash"] == doc.content_hash:
                    report.skipped += 1
                    continue

            # 判断文档是全新还是更新
            is_new = full or existing is None

            # ---- 开始处理 ----
            try:
                chunks = self.chunker.chunk(doc)
                vectors = self.embedder.embed([c.content for c in chunks])

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

                # 更新 processed_docs
                self.sqlite_store.upsert_processed(doc)

                if is_new:
                    report.new += 1
                else:
                    report.updated += 1

            except Exception as e:
                logger.exception("文档处理失败", extra={"source_id": doc.source_id, "error": str(e)})
                report.failed += 1
                error_event = ErrorEvent(
                    source_id=doc.source_id,
                    error=str(e),
                    exception=e,
                )
                report.errors.append(error_event)
                if self._on_error:
                    self._on_error(error_event)
            finally:
                if on_document_done:
                    on_document_done()

        logger.info("Pipeline 执行完成", extra={"total": report.total, "new": report.new, "updated": report.updated, "skipped": report.skipped, "failed": report.failed})
        return report
