"""ZRAG API 视图

提供文档摄入、来源列表等业务 API 的 ViewSet 实现。
"""

import json
import logging
import uuid

from rest_framework import viewsets

from zrag.api.auth import APIKeyAuthentication
from zrag.api.exceptions import LLMCallException, NotFoundException
from zrag.api.response import APIResponse
from zrag.api.serializers import ConversationQuerySerializer, IngestSerializer
from zrag.api.throttles import ChatRateThrottle, IngestRateThrottle
from zrag.ingest.pipeline import IngestionPipeline
from zrag.ingest.sources import SOURCE_REGISTRY
from zrag.retrieval.prompt_builder import build_rag_prompt
from zrag.store.sqlite_store import SQLiteStore, get_sqlite_store

logger = logging.getLogger(__name__)


def _get_request_id(request):
    """从 request 中提取 X-Request-ID"""
    return getattr(request, 'META', {}).get("X-Request-ID", "-")


class DocumentViewSet(viewsets.ViewSet):
    """文档管理视图集

    提供文档摄入和来源列表的 API 端点。
    ingest 端点通过 SOURCE_REGISTRY 获取 Source 实例并执行摄入流程。
    list_sources 端点查询 processed_docs 表返回来源统计信息。

    @param authentication_classes: DRF 认证类列表, 使用 Bearer Token API Key 认证
    @type  authentication_classes: list
    """

    authentication_classes = [APIKeyAuthentication]
    throttle_classes = [IngestRateThrottle]

    def ingest(self, request):
        """执行文档摄入

        接收 POST /v1/documents/ingest 请求,
        校验请求体参数后通过 SOURCE_REGISTRY 获取 Source 实例,
        调用 IngestionPipeline.run(source, full=full) 执行摄入流程,
        返回 IngestReport 格式的处理结果。

        @param request: DRF 请求对象, 请求体需包含 source_type(可选) 和 full(可选)
        @type  request: rest_framework.request.Request

        @raises ValueError: 当 source_type 未在 SOURCE_REGISTRY 中注册时抛出, 返回 400
        @type  ValueError

        @raises Exception: 摄入流程执行过程中发生的其他异常, 由全局异常处理器转换为 500
        @type  Exception

        @return: 包含摄入报告的 APIResponse, http_status 200
        @rtype:  rest_framework.response.Response
        """
        serializer = IngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        source_type = serializer.validated_data.get("source_type", None)
        full = serializer.validated_data.get("full", False)

        if source_type is None:
            source_type = next(iter(SOURCE_REGISTRY))

        req_id = _get_request_id(request)
        logger.info("[req=%s] 开始文档摄入 source_type=%s full=%s", req_id, source_type, full)

        source_cls = SOURCE_REGISTRY.get(source_type)
        if source_cls is None:
            return APIResponse(
                data=None,
                message=f"Unknown source_type: {source_type}",
                http_status=400,
                request=request,
            )

        from zrag.embed.local import get_embedder
        from zrag.ingest.chunking.registry import get_chunker
        from zrag.store.vector_store import get_chroma_store

        source = source_cls()
        store = SQLiteStore()
        chroma_store = get_chroma_store()
        embedder = get_embedder()
        chunker = get_chunker(source_type)
        pipeline = IngestionPipeline(
            sqlite_store=store,
            chroma_store=chroma_store,
            embedder=embedder,
            chunker=chunker,
        )
        logger.info("[req=%s] Pipeline 已初始化 source_type=%s", req_id, source_type)
        try:
            report = pipeline.run(source=source, full=full)
        except Exception:
            logger.exception("[req=%s] 摄入失败 source_type=%s", req_id, source_type)
            raise
        logger.info(
            "[req=%s] 摄入完成 source_type=%s total=%d new=%d updated=%d skipped=%d failed=%d",
            req_id, source_type, report.total, report.new, report.updated,
            report.skipped, report.failed,
        )

        return APIResponse(
            data={
                "total": report.total,
                "new": report.new,
                "updated": report.updated,
                "skipped": report.skipped,
                "failed": report.failed,
                "errors": [
                    {"source_id": e.source_id, "error": e.error}
                    for e in report.errors
                ],
            },
            message="success",
            http_status=200,
            request=request,
        )

    def list_sources(self, request):
        """查询文档来源列表

        接收 GET /v1/sources 请求,
        查询 processed_docs 表, 按 source_type 分组统计文档数量,
        返回各来源的文档概况。

        @param request: DRF 请求对象
        @type  request: rest_framework.request.Request

        @return: 包含来源统计列表的 APIResponse, http_status 200
        @rtype:  rest_framework.response.Response
        """
        store = SQLiteStore()
        rows = store.fetch_all(
            "SELECT source_type, COUNT(*) AS doc_count, "
            "MAX(imported_at) AS last_imported "
            "FROM processed_docs "
            "GROUP BY source_type "
            "ORDER BY source_type"
        )
        sources = [
            {
                "source_type": r["source_type"],
                "doc_count": r["doc_count"],
                "last_imported": r["last_imported"],
            }
            for r in rows
        ]

        req_id = _get_request_id(request)
        logger.info("[req=%s] 来源列表已查询 count=%d", req_id, len(sources))
        return APIResponse(
            data={"sources": sources},
            message="success",
            http_status=200,
            request=request,
        )
class ConversationViewSet(viewsets.ViewSet):
    """会话相关视图集

    提供五个端点:
    - GET    /v1/conversations                  — 会话列表, 按最近消息时间倒序
    - GET    /v1/conversations/{id}/messages    — 获取指定会话的消息列表
    - DELETE /v1/conversations/{id}             — 删除指定会话及其所有消息 (幂等)
    - POST   /v1/conversations                  — 创建新会话并触发 RAG 问答
    - POST   /v1/conversations/{id}/messages    — 在已有会话中追加问题并触发 RAG 问答

    store / retriever / llm_provider 属性均可通过构造参数或类属性注入,
    用于测试 mock。默认通过 _get_store() / _get_retriever() / _get_llm() 懒加载。
    """

    authentication_classes = [APIKeyAuthentication]
    throttle_classes = [ChatRateThrottle]

    store = None
    retriever = None
    llm_provider = None

    def _get_store(self):
        """获取 SQLiteStore 实例

        优先使用实例属性 self.store, 若未设置则回退到模块级单例工厂。

        @return: SQLiteStore 实例
        @type:   SQLiteStore
        """
        if hasattr(self, 'store') and self.store is not None:
            return self.store
        return get_sqlite_store()

    def _get_retriever(self):
        """获取 Retriever 实例 (懒加载)

        优先使用实例属性 self.retriever, 若未设置则根据
        self.chroma_store / self.embedder 构建。
        若 chroma_store 或 embedder 未注入, 则使用默认实例 (从配置读取)。

        @return: Retriever 实例
        @rtype:  Retriever
        """
        if hasattr(self, 'retriever') and self.retriever is not None:
            return self.retriever
        from zrag.embed.local import get_embedder
        from zrag.retrieval.retriever import Retriever
        from zrag.store.vector_store import get_chroma_store
        chroma = (
            self.chroma_store
            if hasattr(self, 'chroma_store') and self.chroma_store is not None
            else get_chroma_store()
        )
        emb = (
            self.embedder
            if hasattr(self, 'embedder') and self.embedder is not None
            else get_embedder()
        )
        store = self._get_store()
        self.retriever = Retriever(
            sqlite_store=store,
            chroma_store=chroma,
            embedder=emb,
        )
        return self.retriever

    def _get_llm(self):
        """获取 LLMProvider 实例 (懒加载)

        优先使用实例属性 self.llm_provider, 若未设置则创建默认的
        LLMGatewayProvider 实例。

        @return: LLMProvider 实例
        @rtype:  LLMProvider
        """
        if hasattr(self, 'llm_provider') and self.llm_provider is not None:
            return self.llm_provider
        from zrag.llm.gateway import LLMGatewayProvider
        self.llm_provider = LLMGatewayProvider()
        return self.llm_provider

    def list(self, request):
        """获取会话列表 (切片 28)

        查询所有会话记录, 按最近消息时间 (last_msg_at) 倒序排列。
        返回结果中包含 total 字段表示会话总数。

        @param request: Django REST Framework 请求对象
        @type  request: rest_framework.request.Request

        @return: 包含会话列表的统一响应
                 data 结构: { "total": int, "conversations": list[dict] }
        @type:   APIResponse
        """
        store = self._get_store()
        rows = store.fetch_all("""
            SELECT c.id, c.title, c.created_at,
                   (SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = c.id) AS last_msg_at
            FROM conversations c ORDER BY last_msg_at DESC
        """)
        req_id = _get_request_id(request)
        logger.debug("[req=%s] 会话列表已查询 count=%d", req_id, len(rows))
        return APIResponse(data={"total": len(rows), "conversations": rows})

    def get_messages(self, request, conversation_id=None):
        """获取指定会话的消息列表 (切片 29)

        查询指定会话的所有消息, 按创建时间正序排列。
        若指定会话不存在, 则返回 404 错误响应。

        @param request: Django REST Framework 请求对象
        @type  request: rest_framework.request.Request
        @param conversation_id: 会话唯一标识, 从 URL 路径参数中提取
        @type  conversation_id: str

        @raises: 当会话不存在时
        @type:   rest_framework.exceptions.NotFound

        @return: 包含消息列表的统一响应
                 data 结构: { "conversation_id": str, "messages": list[dict] }
        @type:   APIResponse
        """
        store = self._get_store()
        conv = store.fetch_one(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,),
        )
        req_id = _get_request_id(request)
        if conv is None:
            logger.warning("[req=%s] 会话不存在 conversation_id=%s", req_id, conversation_id)
            return APIResponse(
                data=None,
                message="conversation not found",
                http_status=404,
            )
        rows = store.fetch_all(
            "SELECT id, role, content, sources, created_at "
            "FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        logger.info("[req=%s] 消息列表已查询 conversation_id=%s count=%d", req_id, conversation_id, len(rows))
        return APIResponse(data={"conversation_id": conversation_id, "messages": rows})

    def destroy(self, request, conversation_id=None):
        """删除指定会话及其所有消息 (切片 30, 幂等)

        先删除该会话下的所有消息, 再删除会话记录。
        若指定会话不存在, 仍返回成功 (幂等性保证)。

        @param request: Django REST Framework 请求对象
        @type  request: rest_framework.request.Request
        @param conversation_id: 会话唯一标识, 从 URL 路径参数中提取
        @type  conversation_id: str

        @return: 包含被删除会话 ID 的统一响应, HTTP 200
                 data 结构: { "deleted": str }
        @type:   APIResponse
        """
        store = self._get_store()
        with store.transaction() as db:
            db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        req_id = _get_request_id(request)
        logger.info("[req=%s] 会话已删除 conversation_id=%s", req_id, conversation_id)
        return APIResponse(data={"deleted": conversation_id})

    def create(self, request):
        """创建新会话并执行 RAG 问答 (切片 26)

        接收 POST /v1/conversations 请求, 请求体需包含 query 字段。
        流程:
          1. 生成 UUID 作为 conversation_id, query 前 50 字符作为 title
          2. 写入 conversations 记录
          3. hybrid_search 检索 + build_rag_prompt 构建消息
          4. LLM 调用获取回复
          5. 写入 user 和 assistant 消息记录
          6. 返回包含会话 ID、用户消息及助手回复的统一响应

        @param request: DRF 请求对象, 请求体需包含 query
        @type  request: rest_framework.request.Request

        @raises ValidationError: 当 query 参数校验不通过时, 由 DRF 自动处理为 400
        @type  rest_framework.exceptions.ValidationError
        @raises LLMCallException: 当 LLM 调用失败且 on_error 未设置时抛出, 转换为 502
        @type  LLMCallException
        @raises NotFoundException: 当会话不存在时抛出, 转换为 404
        @type  NotFoundException

        @return: 包含会话及回复数据的统一响应, HTTP 201
                 data 结构:
                   { "conversation_id": str, "title": str,
                     "user_message": { "id": str, "role": "user", "content": str },
                     "assistant_response": { "id": str, "role": "assistant",
                       "content": str, "sources": list[dict] } }
        @rtype:  APIResponse
        """
        req_id = _get_request_id(request)
        serializer = ConversationQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data["query"]

        conversation_id = str(uuid.uuid4())
        title = query[:50]

        store = self._get_store()
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            (conversation_id, title),
        )

        retriever = self._get_retriever()
        results = retriever.hybrid_search(query, k=10)
        logger.info("[req=%s] 检索完成 conversation_id=%s results_count=%d", req_id, conversation_id, len(results))

        messages = build_rag_prompt(query, results)

        llm = self._get_llm()
        reply = llm.chat(messages)
        if reply is None:
            raise LLMCallException("LLM returned no response")
        logger.info("[req=%s] LLM 调用完成 conversation_id=%s reply_len=%d", req_id, conversation_id, len(reply))

        sources_json = json.dumps(
            [
                {
                    "doc_title": r.doc_title,
                    "source_id": r.source_id,
                    "source_type": r.source_type,
                    "score": r.score,
                }
                for r in results
            ],
            ensure_ascii=False,
        )

        user_msg_id = str(uuid.uuid4())
        assistant_msg_id = str(uuid.uuid4())

        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content) "
            "VALUES (?, ?, ?, ?)",
            (user_msg_id, conversation_id, "user", query),
        )
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content, sources) "
            "VALUES (?, ?, ?, ?, ?)",
            (assistant_msg_id, conversation_id, "assistant", reply, sources_json),
        )
        logger.info("[req=%s] 消息已保存 conversation_id=%s", req_id, conversation_id)

        return APIResponse(
            data={
                "conversation_id": conversation_id,
                "title": title,
                "user_message": {
                    "id": user_msg_id,
                    "role": "user",
                    "content": query,
                },
                "assistant_response": {
                    "id": assistant_msg_id,
                    "role": "assistant",
                    "content": reply,
                    "sources": [
                        {
                            "doc_title": r.doc_title,
                            "source_id": r.source_id,
                            "source_type": r.source_type,
                            "score": r.score,
                        }
                        for r in results
                    ],
                },
            },
            http_status=201,
            request=request,
        )

    def add_message(self, request, conversation_id=None):
        """在已有会话中追加消息并执行 RAG 问答 (切片 27)

        接收 POST /v1/conversations/{id}/messages 请求, 请求体需包含 query 字段。
        流程:
          1. 校验 conversation_id 存在, 不存在则返回 404
          2. 获取该会话最近 10 条消息作为历史上下文
          3. hybrid_search 检索 + build_rag_prompt 构建 system message
          4. 将历史消息插入 system 和 user 之间, 形成完整消息列表
          5. LLM 调用获取回复
          6. 写入 user 和 assistant 消息记录
          7. 返回包含用户消息及助手回复的统一响应

        @param request: DRF 请求对象, 请求体需包含 query
        @type  request: rest_framework.request.Request
        @param conversation_id: 会话唯一标识, 从 URL 路径参数中提取
        @type  conversation_id: str

        @raises ValidationError: 当 query 参数校验不通过时, 由 DRF 自动处理为 400
        @type  rest_framework.exceptions.ValidationError
        @raises NotFoundException: 当会话不存在时抛出, 转换为 404
        @type  NotFoundException
        @raises LLMCallException: 当 LLM 调用失败且 on_error 未设置时抛出, 转换为 502
        @type  LLMCallException

        @return: 包含用户消息及助手回复的统一响应, HTTP 201
                 data 结构:
                   { "conversation_id": str,
                     "user_message": { "id": str, "role": "user", "content": str },
                     "assistant_response": { "id": str, "role": "assistant",
                       "content": str, "sources": list[dict] } }
        @rtype:  APIResponse
        """
        req_id = _get_request_id(request)
        serializer = ConversationQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data["query"]

        store = self._get_store()
        conv = store.fetch_one(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,),
        )
        if conv is None:
            raise NotFoundException(f"Conversation {conversation_id} not found")

        history_rows = store.fetch_all(
            "SELECT role, content FROM messages "
            "WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 10",
            (conversation_id,),
        )
        history = list(reversed(history_rows))
        logger.info("[req=%s] 历史消息已加载 conversation_id=%s history_count=%d", req_id, conversation_id, len(history))

        retriever = self._get_retriever()
        results = retriever.hybrid_search(query, k=10)
        logger.info("[req=%s] 检索完成 conversation_id=%s results_count=%d", req_id, conversation_id, len(results))

        rag_messages = build_rag_prompt(query, results)
        system_msg = rag_messages[0]

        full_messages = [system_msg]
        for h in history:
            full_messages.append({"role": h["role"], "content": h["content"]})
        full_messages.append({"role": "user", "content": query})

        llm = self._get_llm()
        reply = llm.chat(full_messages)
        if reply is None:
            raise LLMCallException("LLM returned no response")
        logger.info("[req=%s] LLM 调用完成 conversation_id=%s reply_len=%d", req_id, conversation_id, len(reply))

        sources_json = json.dumps(
            [
                {
                    "doc_title": r.doc_title,
                    "source_id": r.source_id,
                    "source_type": r.source_type,
                    "score": r.score,
                }
                for r in results
            ],
            ensure_ascii=False,
        )

        user_msg_id = str(uuid.uuid4())
        assistant_msg_id = str(uuid.uuid4())

        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content) "
            "VALUES (?, ?, ?, ?)",
            (user_msg_id, conversation_id, "user", query),
        )
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content, sources) "
            "VALUES (?, ?, ?, ?, ?)",
            (assistant_msg_id, conversation_id, "assistant", reply, sources_json),
        )
        logger.info("[req=%s] 消息已保存 conversation_id=%s", req_id, conversation_id)

        return APIResponse(
            data={
                "conversation_id": conversation_id,
                "user_message": {
                    "id": user_msg_id,
                    "role": "user",
                    "content": query,
                },
                "assistant_response": {
                    "id": assistant_msg_id,
                    "role": "assistant",
                    "content": reply,
                    "sources": [
                        {
                            "doc_title": r.doc_title,
                            "source_id": r.source_id,
                            "source_type": r.source_type,
                            "score": r.score,
                        }
                        for r in results
                    ],
                },
            },
            http_status=201,
            request=request,
        )
