"""健康检查模块

提供进程存活检查和依赖服务健康检查端点。
"""

from rest_framework import viewsets

from zrag.api.response import APIResponse


class HealthViewSet(viewsets.ViewSet):
    """健康检查视图集

    提供两个端点:
    - GET /v1/health/live — 仅检查进程是否存活
    - GET /v1/health/ready — 检查 SQLite 和 ChromaDB 依赖是否可用
    """

    # 跳过认证和限速
    authentication_classes = []
    throttle_classes = []

    def live(self, request):
        """GET /v1/health/live — 进程存活检查, 跳过认证和限速

        @param request: DRF 请求对象
        @type  request: rest_framework.request.Request

        @return: 包含 status=alive 的统一响应
        @rtype:  rest_framework.response.Response
        """
        return APIResponse(data={"status": "alive"})

    def ready(self, request):
        """GET /v1/health/ready — 依赖检查: SQLite + ChromaDB

        分别检查 SQLiteStore 和 ChromaStore 是否正常工作。
        全部正常时返回 ready 状态 (200), 任一异常时返回 not_ready (503)。

        @param request: DRF 请求对象
        @type  request: rest_framework.request.Request

        @return: 包含整体状态和各组件检查结果的统一响应
        @rtype:  rest_framework.response.Response
        """
        checks = {}
        try:
            store = get_sqlite_store()
            store.execute("SELECT 1")
            checks['sqlite'] = 'ok'
        except Exception as e:
            checks['sqlite'] = str(e)
        try:
            store = get_chroma_store()
            store.count()
            checks['chromadb'] = 'ok'
        except Exception as e:
            checks['chromadb'] = str(e)
        all_ok = all(v == 'ok' for v in checks.values())
        return APIResponse(
            data={'status': 'ready' if all_ok else 'not_ready', 'checks': checks},
            http_status=200 if all_ok else 503,
        )


def get_sqlite_store():
    """获取 SQLiteStore 实例

    使用默认路径 data/zrag.db 创建 SQLiteStore 对象实例并返回。

    @return: SQLiteStore 对象实例
    @rtype:  zrag.store.sqlite_store.SQLiteStore
    """
    from zrag.store.sqlite_store import SQLiteStore
    return SQLiteStore()


def get_chroma_store():
    """获取 ChromaStore 实例

    使用默认路径 data/chroma_db 创建 ChromaStore 对象实例并返回。

    @return: ChromaStore 对象实例
    @rtype:  zrag.store.vector_store.ChromaStore
    """
    from zrag.store.vector_store import ChromaStore
    return ChromaStore(persist_dir='data/chroma_db')
