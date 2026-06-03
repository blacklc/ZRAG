"""测试切片 21 — API Key 认证"""
import pytest
from django.test import RequestFactory
from django.test.utils import override_settings
from rest_framework.exceptions import AuthenticationFailed

from zrag.api.auth import APIKeyAuthentication


class TestAPIKeyAuthentication:
    """APIKeyAuthentication 认证测试类"""

    TEST_API_KEY = "test-api-key-12345"

    def _make_request(self, authorization_header=None):
        """创建测试请求

        @param authorization_header: Authorization 请求头值, defaults to None
        @type  authorization_header: str, optional

        @return: Django 测试请求对象
        @rtype:  django.http.HttpRequest
        """
        factory = RequestFactory()
        if authorization_header is not None:
            return factory.get("/test", HTTP_AUTHORIZATION=authorization_header)
        return factory.get("/test")

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_missing_header(self):
        """无 Authorization header 时返回 401"""
        auth = APIKeyAuthentication()
        request = self._make_request()
        with pytest.raises(AuthenticationFailed) as ctx:
            auth.authenticate(request)
        assert "Missing or invalid" in str(ctx.value)

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_invalid_key(self):
        """Key 不匹配时返回 401"""
        auth = APIKeyAuthentication()
        request = self._make_request(
            authorization_header="Bearer invalid-key-99999",
        )
        with pytest.raises(AuthenticationFailed) as ctx:
            auth.authenticate(request)
        assert "Invalid API key" in str(ctx.value)

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_valid_key(self):
        """Key 匹配时认证通过"""
        auth = APIKeyAuthentication()
        request = self._make_request(
            authorization_header=f"Bearer {self.TEST_API_KEY}",
        )
        result = auth.authenticate(request)
        assert result == (None, None)

    @override_settings(ZRAG_API_KEY="")
    def test_env_var_fallback(self):
        """当 settings.ZRAG_API_KEY 为空时, 回退到环境变量 ZRAG_API_KEY"""
        import os
        os.environ["ZRAG_API_KEY"] = "env-key"
        try:
            auth = APIKeyAuthentication()
            request = self._make_request(authorization_header="Bearer env-key")
            result = auth.authenticate(request)
            assert result == (None, None)
        finally:
            os.environ.pop("ZRAG_API_KEY", None)
