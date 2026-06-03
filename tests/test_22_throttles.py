"""切片 22 — 速率限制功能测试

验证 ChatRateThrottle 和 IngestRateThrottle 的速率限制行为,
以及不同 scope 之间的独立计数。
"""

from django.core.cache import cache
from django.test import override_settings
from django.urls import path
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from zrag.api.throttles import ChatRateThrottle, IngestRateThrottle

# ---------------------------------------------------------------------------
# 测试用视图
# ---------------------------------------------------------------------------


class _ChatTestView(APIView):
    """测试 Chat 速率限制的视图

    使用 ChatRateThrottle 限制请求频率。
    """

    throttle_classes = [ChatRateThrottle]

    def get(self, request):
        """返回成功响应

        @param request: DRF 请求对象
        @type  request: rest_framework.request.Request

        @return: 成功响应, 包含状态信息
        @rtype:  rest_framework.response.Response
        """
        return Response({"status": "ok"})


class _IngestTestView(APIView):
    """测试 Ingest 速率限制的视图

    使用 IngestRateThrottle 限制请求频率。
    """

    throttle_classes = [IngestRateThrottle]

    def get(self, request):
        """返回成功响应

        @param request: DRF 请求对象
        @type  request: rest_framework.request.Request

        @return: 成功响应, 包含状态信息
        @rtype:  rest_framework.response.Response
        """
        return Response({"status": "ok"})


# ---------------------------------------------------------------------------
# 测试用 URL 配置
# ---------------------------------------------------------------------------

urlpatterns = [
    path("api/test/chat/", _ChatTestView.as_view(), name="test-chat"),
    path("api/test/ingest/", _IngestTestView.as_view(), name="test-ingest"),
]

# ---------------------------------------------------------------------------
# 速率限制配置（用于 override_settings）
# ---------------------------------------------------------------------------

_THROTTLE_RATES = {
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "chat": "10/min",
        "ingest": "3/min",
    },
    # 避免 DRF 默认 UNAUTHENTICATED_USER 自动导入 django.contrib.auth.models,
    # 因为该 app 未被包含在 INSTALLED_APPS 中。
    "UNAUTHENTICATED_USER": None,
    "UNAUTHENTICATED_TOKEN": None,
}

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


class TestThrottles:
    """速率限制功能测试类

    测试 ChatRateThrottle 和 IngestRateThrottle 的速率限制行为。
    """

    def setup_method(self):
        """每个测试方法执行前清空缓存

        确保速率限制计数从零开始,
        避免测试方法之间的计数污染。
        """
        cache.clear()

    def _make_client(self):
        """创建测试客户端

        @return: DRF 测试客户端实例
        @rtype:  rest_framework.test.APIClient
        """
        return APIClient()

    # ---- 测试用例 ----

    @override_settings(ROOT_URLCONF=__name__, REST_FRAMEWORK=_THROTTLE_RATES)
    def test_chat_throttle(self):
        """测试 Chat 接口 10 req/min 限制

        发送 10 次请求应全部成功,
        第 11 次应返回 429 状态码表示被限流。
        """
        client = self._make_client()

        # 前 10 次应成功
        for i in range(10):
            resp = client.get("/api/test/chat/")
            assert resp.status_code == 200, f"第 {i + 1} 次请求应成功, 但得到 {resp.status_code}"

        # 第 11 次应被限流
        resp = client.get("/api/test/chat/")
        assert resp.status_code == 429, f"第 11 次请求应被限流, 但得到 {resp.status_code}"

    @override_settings(ROOT_URLCONF=__name__, REST_FRAMEWORK=_THROTTLE_RATES)
    def test_ingest_throttle(self):
        """测试 Ingest 接口 3 req/min 限制

        发送 3 次请求应全部成功,
        第 4 次应返回 429 状态码表示被限流。
        """
        client = self._make_client()

        # 前 3 次应成功
        for i in range(3):
            resp = client.get("/api/test/ingest/")
            assert resp.status_code == 200, f"第 {i + 1} 次请求应成功, 但得到 {resp.status_code}"

        # 第 4 次应被限流
        resp = client.get("/api/test/ingest/")
        assert resp.status_code == 429, f"第 4 次请求应被限流, 但得到 {resp.status_code}"

    @override_settings(ROOT_URLCONF=__name__, REST_FRAMEWORK=_THROTTLE_RATES)
    def test_different_scopes_independent(self):
        """验证 chat 和 ingest 的速率限制计数互不干扰

        先耗尽 chat 的配额（10 次）, 此时 chat 被限流,
        但 ingest 应该仍有完整的 3 次可用配额。
        """
        client = self._make_client()

        # 步骤 1 — 消耗 chat 配额（10 次）
        for i in range(10):
            resp = client.get("/api/test/chat/")
            assert resp.status_code == 200, f"chat 第 {i + 1} 次请求应成功, 但得到 {resp.status_code}"

        # chat 的第 11 次应被限流
        resp = client.get("/api/test/chat/")
        assert resp.status_code == 429, "chat 第 11 次请求应被限流"

        # 步骤 2 — ingest 应仍然有独立的 3 次可用配额
        for i in range(3):
            resp = client.get("/api/test/ingest/")
            assert resp.status_code == 200, f"ingest 第 {i + 1} 次请求应成功, 但得到 {resp.status_code}"

        # ingest 的第 4 次应被限流
        resp = client.get("/api/test/ingest/")
        assert resp.status_code == 429, "ingest 第 4 次请求应被限流"
