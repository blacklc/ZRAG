"""ZRAG API 视图

提供文档摄入、来源列表等业务 API 的 ViewSet 实现。
"""

import logging

from rest_framework import viewsets

from zrag.api.auth import APIKeyAuthentication
from zrag.api.response import APIResponse
from zrag.api.serializers import IngestSerializer
from zrag.api.throttles import IngestRateThrottle
from zrag.ingest.pipeline import IngestionPipeline
from zrag.ingest.sources import SOURCE_REGISTRY
from zrag.store.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


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
            # 未指定 source_type 时默认使用第一个注册的来源类型
            source_type = next(iter(SOURCE_REGISTRY))

        source_cls = SOURCE_REGISTRY.get(source_type)
        if source_cls is None:
            return APIResponse(
                data=None,
                message=f"Unknown source_type: {source_type}",
                http_status=400,
                request=request,
            )

        source = source_cls()
        store = SQLiteStore()
        pipeline = IngestionPipeline(
            sqlite_store=store,
            chroma_store=None,
            embedder=None,
            chunker=None,
        )
        report = pipeline.run(source=source, full=full)

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

        return APIResponse(
            data={"sources": sources},
            message="success",
            http_status=200,
            request=request,
        )
class ConversationViewSet(viewsets.ViewSet):
    """会话相关视图集

    提供三个端点:
    - GET  /v1/conversations              — 会话列表, 按最近消息时间倒序
    - GET  /v1/conversations/{id}/messages — 获取指定会话的消息列表
    - DELETE /v1/conversations/{id}        — 删除指定会话及其所有消息 (幂等)

    store 属性可通过构造参数或类属性注入, 默认为 None 时会自动通过 get_sqlite_store() 获取。
    """

    store = None

    def _get_store(self):
        """获取 SQLiteStore 实例

        优先使用实例属性 self.store, 若未设置则回退到模块级单例工厂。

        @return: SQLiteStore 实例
        @type:   SQLiteStore
        """
        if hasattr(self, 'store') and self.store is not None:
            return self.store
        return get_sqlite_store()

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
        if conv is None:
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
        return APIResponse(data={"deleted": conversation_id})
