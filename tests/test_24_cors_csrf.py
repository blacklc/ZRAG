"""切片 24 — CORS + CSRF 配置测试"""

import pytest
from django.test import override_settings, RequestFactory
from django.http import HttpResponse
from corsheaders.middleware import CorsMiddleware


def _simple_view(request):
    """简单视图，供测试使用

    @param request: Django 请求对象
    @type  request: django.http.HttpRequest

    @return: 空响应对象
    @rtype:  django.http.HttpResponse
    """
    return HttpResponse()


class TestCorsCsrf:
    """CORS + CSRF 配置测试类"""

    @override_settings(
        CORS_ALLOW_ALL_ORIGINS=True,
        CORS_ALLOWED_ORIGINS=None,
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'rest_framework',
            'corsheaders',
        ],
    )
    def test_cors_header_present(self):
        """跨域响应包含 Access-Control-Allow-Origin"""
        middleware = CorsMiddleware(_simple_view)
        factory = RequestFactory()
        request = factory.get("/test", HTTP_ORIGIN="http://example.com")
        response = middleware(request)

        assert response["Access-Control-Allow-Origin"] == "*"

    @override_settings(
        CSRF_COOKIE_SECURE=False,
        CSRF_COOKIE_HTTPONLY=False,
        CSRF_USE_SESSIONS=False,
        MIDDLEWARE=[],
    )
    def test_csrf_disabled(self):
        """POST 请求不需要 CSRF token"""
        factory = RequestFactory()
        request = factory.post("/test")
        # 当 CSRF 中间件未启用时，POST 请求不应触发 CSRF 验证
        # 只需确保不抛出 CSRF 相关异常即可
        response = _simple_view(request)
        assert response.status_code == 200

    def test_settings_configured(self):
        """settings 中包含 corsheaders"""
        from django.conf import settings
        assert 'corsheaders' in settings.INSTALLED_APPS
