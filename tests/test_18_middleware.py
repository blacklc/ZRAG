import uuid
import re

from django.test import RequestFactory
from django.http import HttpResponse

from zrag.api.middleware import RequestIDMiddleware


def _get_response(request):
    """简单视图函数, 供中间件测试使用

    @param request: Django 请求对象
    @type  request: django.http.HttpRequest

    @return: 空响应对象
    @rtype:  django.http.HttpResponse
    """
    return HttpResponse()


class TestRequestIDMiddleware:
    """RequestIDMiddleware 测试类"""

    def _make_middleware(self):
        """创建 RequestIDMiddleware 实例

        @return: RequestIDMiddleware 实例
        @rtype:  RequestIDMiddleware
        """
        return RequestIDMiddleware(_get_response)

    def test_request_id_generated(self):
        """无请求头时自动生成 X-Request-ID"""
        middleware = self._make_middleware()
        factory = RequestFactory()
        request = factory.get("/test")
        response = middleware(request)

        assert "X-Request-ID" in response
        request_id = response["X-Request-ID"]
        # 验证是合法的 UUID 格式
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            request_id,
        )

    def test_request_id_passed_through(self):
        """请求头 X-Request-ID 被透传到响应"""
        expected_id = str(uuid.uuid4())
        middleware = self._make_middleware()
        factory = RequestFactory()
        request = factory.get("/test", HTTP_X_REQUEST_ID=expected_id)
        response = middleware(request)

        assert response["X-Request-ID"] == expected_id

    def test_request_id_in_meta(self):
        """request.META 中包含 X-Request-ID"""
        middleware = self._make_middleware()
        factory = RequestFactory()
        request = factory.get("/test")
        middleware(request)

        assert "X-Request-ID" in request.META
        request_id = request.META["X-Request-ID"]
        # 验证是合法的 UUID 格式
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            request_id,
        )

    def test_request_id_in_meta_with_header(self):
        """当请求头包含 X-Request-ID 时, request.META 中沿用该值"""
        expected_id = str(uuid.uuid4())
        middleware = self._make_middleware()
        factory = RequestFactory()
        request = factory.get("/test", HTTP_X_REQUEST_ID=expected_id)
        middleware(request)

        assert request.META["X-Request-ID"] == expected_id
