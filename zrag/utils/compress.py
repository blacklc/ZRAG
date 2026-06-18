"""异步压缩服务

提供对话摘要的异步压缩能力。复用项目全局线程池提交压缩任务到后台线程执行，
不阻塞请求响应。压缩失败静默降级，仅记录错误日志。
"""

import logging
import threading

from zrag.llm.gateway import LLMGatewayProvider
from zrag.retrieval.conversation_summarizer import ConversationSummarizer
from zrag.store.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

_compressor = None
_lock = threading.Lock()


def get_compress_service():
    """获取 CompressService 全局单例

    首次调用时从 Django settings 读取配置并初始化。
    后续调用直接返回已有实例。DoLC 懒加载线程安全。

    @return: CompressService 单例实例
    @rtype:  CompressService
    """
    global _compressor
    if _compressor is None:
        with _lock:
            if _compressor is None:
                from django.conf import settings

                rewriter_llm = LLMGatewayProvider(
                    model=settings.ZRAG_LLM["gateway"]["rewriter_model"],
                )
                _compressor = CompressService(
                    executor=settings.ZRAG_INGEST_EXECUTOR,
                    llm_provider=rewriter_llm,
                )
    return _compressor


class CompressService:
    """异步压缩服务

    复用项目全局线程池（ZRAG_INGEST_EXECUTOR）异步执行对话压缩。
    不阻塞请求响应，压缩失败静默降级。
    """

    def __init__(self, executor, llm_provider):
        """构造 CompressService

        @param executor:     ThreadPoolExecutor 实例
        @type  executor:     ThreadPoolExecutor
        @param llm_provider: LLMProvider 实例，需实现 chat(messages) -> str | None
        @type  llm_provider: object
        """
        self._executor = executor
        self._summarizer = ConversationSummarizer(llm_provider=llm_provider)

    def submit(self, conversation_id, old_summary, user_query, assistant_reply):
        """提交异步压缩任务到线程池，立即返回（不等待结果）

        @param conversation_id: 会话 ID
        @type  conversation_id:  str
        @param old_summary:      已有摘要（空字符串表示首轮）
        @type  old_summary:      str
        @param user_query:       本轮用户查询文本
        @type  user_query:       str
        @param assistant_reply:  本轮助手回复文本
        @type  assistant_reply:  str
        """
        logger.info(
            "压缩任务提交: conversation_id=%s old_summary_len=%d",
            conversation_id, len(old_summary),
        )
        self._executor.submit(
            self._run,
            conversation_id,
            old_summary,
            user_query,
            assistant_reply,
        )

    def _run(self, conversation_id, old_summary, user_query, assistant_reply):
        """压缩线程主逻辑（在线程池工作线程中执行）

        1. 调用 ConversationSummarizer.summarize() 生成摘要
        2. 通过新的 SqliteStore 实例写入 DB（无参数构造，从 settings 读取路径）
        3. 任何异常静默捕获，仅记日志，不重试

        @param conversation_id: 会话 ID
        @type  conversation_id:  str
        @param old_summary:      已有摘要
        @type  old_summary:      str
        @param user_query:       本轮用户查询
        @type  user_query:       str
        @param assistant_reply:  本轮助手回复
        @type  assistant_reply:  str
        """
        try:
            new_summary = self._summarizer.summarize(
                old_summary=old_summary,
                user_query=user_query,
                assistant_reply=assistant_reply,
            )
        except Exception:
            logger.exception(
                "压缩 LLM 调用失败 conversation_id=%s", conversation_id
            )
            return

        if not new_summary:
            logger.warning(
                "压缩结果为空 conversation_id=%s", conversation_id,
            )
            return

        try:
            store = SQLiteStore()  # 独立实例，独立连接
            store.execute(
                "UPDATE conversations SET summary = ?, summary_updated_at = datetime('now') WHERE id = ?",
                (new_summary, conversation_id),
            )
            logger.info(
                "摘要已写入 conversation_id=%s summary_len=%d",
                conversation_id,
                len(new_summary),
            )
        except Exception:
            logger.exception(
                "摘要写入 DB 失败 conversation_id=%s", conversation_id
            )
