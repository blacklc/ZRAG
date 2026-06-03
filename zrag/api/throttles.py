"""ZRAG API 速率限制器

基于 DRF 的 SimpleRateThrottle 实现,
提供针对不同接口范围的独立速率限制控制。

注意: 此处选择 SimpleRateThrottle 而非 ScopedRateThrottle,
因为 ScopedRateThrottle 的 allow_request 会从视图的 throttle_scope
属性获取 scope, 忽略类级别的 scope 属性。而 SimpleRateThrottle
直接使用类级别的 scope, 更符合本项目的使用方式。
"""

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class _ThrottleRatesMixin:
    """THROTTLE_RATES 动态读取与缓存键生成混入类

    SimpleRateThrottle 将 THROTTLE_RATES 定义为类属性,
    该属性在模块导入时求值, 不会响应 override_settings 等
    运行时配置变更。此混入类将其改为 property,
    每次访问时从 api_settings 读取, 确保测试中
    override_settings(REST_FRAMEWORK=...) 能够生效。

    @param THROTTLE_RATES: 当前 DRF 速率限制配置
    @type  THROTTLE_RATES: dict
    """

    @property
    def THROTTLE_RATES(self):
        """获取当前 DRF 的速率限制配置字典

        @return: scope 到速率配置字符串的映射, 例如 {"chat": "10/min"}
        @rtype:  dict
        """
        return api_settings.DEFAULT_THROTTLE_RATES

    def get_cache_key(self, request, view):
        """生成用于速率限制计数的缓存键

        基于客户端 IP 和 scope 生成唯一缓存键,
        确保同一 IP 对同一 scope 的请求共享配额。

        @param request: DRF 请求对象
        @type  request: rest_framework.request.Request
        @param view: 视图实例
        @type  view: rest_framework.views.APIView

        @return: 缓存键字符串, 格式为 "throttle_<scope>_<ip>"
        @rtype:  str
        """
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class ChatRateThrottle(_ThrottleRatesMixin, SimpleRateThrottle):
    """聊天接口速率限制器

    用于限制聊天 API 的请求频率,
    对应的速率配置 key 为 "chat"。

    @param scope: 速率限制范围名称
    @type  scope: str
    """

    scope = "chat"


class IngestRateThrottle(_ThrottleRatesMixin, SimpleRateThrottle):
    """数据接入接口速率限制器

    用于限制数据接入 API 的请求频率,
    对应的速率配置 key 为 "ingest"。

    @param scope: 速率限制范围名称
    @type  scope: str
    """

    scope = "ingest"
