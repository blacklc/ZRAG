"""API Key 认证模块

提供基于 Bearer Token 的 API Key 认证机制,
基于 Django REST Framework 的 BaseAuthentication 实现。
"""

import os

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class APIKeyAuthentication(BaseAuthentication):
    """API Key 认证类

    从 Authorization header 中提取 Bearer token 作为 API Key。
    所有 API 端点（除健康检查外）都需要认证。
    Phase 1: Key 从配置或环境变量读取, 硬编码比对。
    """

    def authenticate(self, request):
        """执行 API Key 认证

        从 Authorization header 中提取 Bearer token,
        并与 settings.ZRAG_API_KEY 或环境变量 ZRAG_API_KEY 进行比对。

        @param request: Django REST Framework 请求对象
        @type  request: rest_framework.request.Request

        @raises AuthenticationFailed: 当 Authorization header 缺失或格式错误时抛出
        @raises AuthenticationFailed: 当 API Key 不匹配时抛出

        @return: (None, None) 表示认证通过, 遵循 DRF 单用户系统约定
        @rtype:  tuple
        """
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            raise AuthenticationFailed("Missing or invalid Authorization header")
        api_key = auth[7:]
        if not self._validate_key(api_key):
            raise AuthenticationFailed("Invalid API key")
        return (None, None)

    def _validate_key(self, api_key: str) -> bool:
        """校验 API Key 是否匹配

        优先级顺序：settings.ZRAG_API_KEY（来自 config/api.yaml） > 环境变量 ZRAG_API_KEY。
        当所有来源均未提供有效的 API Key 时抛出 ValueError。

        @param api_key: 待校验的 API Key
        @type  api_key: str

        @return: True 表示 Key 匹配, False 表示不匹配
        @rtype:  bool

        @raises ValueError: 所有来源均未配置 API Key 时抛出
        """
        expected = getattr(settings, "ZRAG_API_KEY", None)
        if not expected:
            expected = os.environ.get("ZRAG_API_KEY", "")
        if not expected:
            raise ValueError("配置缺失: api.key, 请检查 config/api.yaml 或设置 ZRAG_API_KEY 环境变量")
        return api_key == expected
