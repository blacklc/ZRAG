"""API 异常处理器注册表

基于 Handler Registry 模式, 为每种 BaseZragException 子类注册对应的处理器。
每个处理器负责将异常转换为 DRF Response 对象。

使用方式:
    response = api_exception_handler(exc, context)

参考 zonebank 的 exception_handler.py 模式实现。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type

import logging

from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    ParseError,
    ValidationError,
)
from rest_framework.response import Response

from zrag.api.exceptions import (
    IngestionException,
    LLMCallException,
    NotFoundException,
    RetrievalException,
    UnauthorizedException,
)
from zrag.exception.base import BaseZragException


class BaseAPIExceptionHandler(ABC):
    """API 异常处理器基类

    所有异常处理器应继承此类并实现 handle 方法。

    @param exc: 异常实例
    @type  exc: Exception
    @param context: 异常上下文信息, 包含 request 等
    @type  context: dict
    """

    @abstractmethod
    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """将异常转换为 DRF Response

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息, 包含 request 等
        @type  context: dict

        @return: DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        ...


def _build_error_response(
    exc: BaseZragException, context: Dict[str, Any]
) -> Response:
    """构建统一的错误响应

    从异常中提取 status_code、error_code 和 message,
    构造与 APIResponse 风格一致的错误响应体。

    @param exc: BaseZragException 实例
    @type  exc: BaseZragException
    @param context: 异常上下文信息
    @type  context: dict

    @return: DRF Response 对象
    @rtype:  rest_framework.response.Response
    """
    request = context.get("request")
    request_id = ""
    if request:
        request_id = request.META.get("X-Request-ID", "")
    body = {
        "Message": str(exc),
        "Data": None,
        "RequestID": request_id,
        "ErrorCode": exc.error_code,
    }
    return Response(body, status=exc.status_code)


class DefaultErrorHandler(BaseAPIExceptionHandler):
    """默认异常处理器（兜底）

    处理未知异常类型, 返回 500 Internal Server Error。
    记录完整 traceback 到日志以便排查。
    """

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """将未知异常转换为 500 Response

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 500 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        _logger = logging.getLogger(__name__)
        _logger.exception("未预期的异常: %s", exc)
        request = context.get("request")
        request_id = ""
        if request:
            request_id = request.META.get("X-Request-ID", "")
        body = {
            "Message": "Internal server error",
            "Data": None,
            "RequestID": request_id,
            "ErrorCode": "INTERNAL-ERROR",
        }
        return Response(body, status=500)


class UnauthorizedHandler(BaseAPIExceptionHandler):
    """UnauthorizedException 处理器"""

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 UnauthorizedException

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 401 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        return _build_error_response(exc, context)


class NotFoundHandler(BaseAPIExceptionHandler):
    """NotFoundException 处理器"""

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 NotFoundException

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 404 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        return _build_error_response(exc, context)


class RetrievalHandler(BaseAPIExceptionHandler):
    """RetrievalException 处理器"""

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 RetrievalException

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 500 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        return _build_error_response(exc, context)


class LLMCallHandler(BaseAPIExceptionHandler):
    """LLMCallException 处理器"""

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 LLMCallException

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 502 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        return _build_error_response(exc, context)


class IngestionHandler(BaseAPIExceptionHandler):
    """IngestionException 处理器"""

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 IngestionException

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 500 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        return _build_error_response(exc, context)


class DRFAuthenticationFailedHandler(BaseAPIExceptionHandler):
    """DRF AuthenticationFailed 处理器

    DRF 内置的 AuthenticationFailed 不是 BaseZragException 的子类,
    需要单独处理以确保 401 响应格式与项目统一。
    """

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 DRF AuthenticationFailed

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 401 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        request = context.get("request")
        request_id = ""
        if request:
            request_id = request.META.get("X-Request-ID", "")
        body = {
            "Message": str(exc),
            "Data": None,
            "RequestID": request_id,
            "ErrorCode": "UNAUTHORIZED",
        }
        return Response(body, status=401)


class DRFParseErrorHandler(BaseAPIExceptionHandler):
    """DRF ParseError 处理器

    处理请求体解析失败（如无效 JSON）的情况。
    """

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 DRF ParseError

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 400 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        request = context.get("request")
        request_id = ""
        if request:
            request_id = request.META.get("X-Request-ID", "")
        body = {
            "Message": str(exc),
            "Data": None,
            "RequestID": request_id,
            "ErrorCode": "PARSE-ERROR",
        }
        return Response(body, status=400)


class DRFValidationErrorHandler(BaseAPIExceptionHandler):
    """DRF ValidationError 处理器

    处理请求参数校验失败的情况。
    """

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理 DRF ValidationError

        @param exc: 异常实例
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 400 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        request = context.get("request")
        request_id = ""
        if request:
            request_id = request.META.get("X-Request-ID", "")
        body = {
            "Message": str(exc),
            "Data": None,
            "RequestID": request_id,
            "ErrorCode": "VALIDATION-ERROR",
        }
        return Response(body, status=400)


class DRFGenericAPIExceptionHandler(BaseAPIExceptionHandler):
    """DRF APIException 通用处理器（兜底）

    处理除上述已注册类型之外的其他 DRF APIException 子类。
    从 exc.status_code 获取 HTTP 状态码。
    """

    def handle(self, exc: Exception, context: Dict[str, Any]) -> Response:
        """处理通用的 DRF APIException

        @param exc: 异常实例（必须是 APIException 的子类）
        @type  exc: Exception
        @param context: 异常上下文信息
        @type  context: dict

        @return: 根据 exc.status_code 确定状态码的 DRF Response 对象
        @rtype:  rest_framework.response.Response
        """
        request = context.get("request")
        request_id = ""
        if request:
            request_id = request.META.get("X-Request-ID", "")
        status_code = getattr(exc, "status_code", 500)
        body = {
            "Message": str(exc),
            "Data": None,
            "RequestID": request_id,
            "ErrorCode": "API-ERROR",
        }
        return Response(body, status=status_code)


# 错误类型注册表
# 按优先级排序: 越具体的异常类型越靠前
error_type: List[Dict[str, Any]] = [
    {
        "exception_class": AuthenticationFailed,
        "handler_class": DRFAuthenticationFailedHandler,
        "handler_instance": DRFAuthenticationFailedHandler(),
    },
    {
        "exception_class": UnauthorizedException,
        "handler_class": UnauthorizedHandler,
        "handler_instance": UnauthorizedHandler(),
    },
    {
        "exception_class": ParseError,
        "handler_class": DRFParseErrorHandler,
        "handler_instance": DRFParseErrorHandler(),
    },
    {
        "exception_class": ValidationError,
        "handler_class": DRFValidationErrorHandler,
        "handler_instance": DRFValidationErrorHandler(),
    },
    {
        "exception_class": NotFoundException,
        "handler_class": NotFoundHandler,
        "handler_instance": NotFoundHandler(),
    },
    {
        "exception_class": RetrievalException,
        "handler_class": RetrievalHandler,
        "handler_instance": RetrievalHandler(),
    },
    {
        "exception_class": LLMCallException,
        "handler_class": LLMCallHandler,
        "handler_instance": LLMCallHandler(),
    },
    {
        "exception_class": IngestionException,
        "handler_class": IngestionHandler,
        "handler_instance": IngestionHandler(),
    },
    {
        "exception_class": APIException,
        "handler_class": DRFGenericAPIExceptionHandler,
        "handler_instance": DRFGenericAPIExceptionHandler(),
    },
]


def api_exception_handler(exc: Exception, context: Dict[str, Any]) -> Response:
    """API 异常处理入口函数

    遍历 error_type 注册表, 查找匹配的异常类型处理器。
    若未找到匹配项则使用 DefaultErrorHandler 兜底。

    @param exc: 异常实例
    @type  exc: Exception
    @param context: 异常上下文信息, 包含 request 等
    @type  context: dict

    @raises: 无 — 所有异常均被捕获并转换为 Response
    @type:   None

    @return: DRF Response 对象
    @rtype:  rest_framework.response.Response
    """
    for entry in error_type:
        if isinstance(exc, entry["exception_class"]):
            return entry["handler_instance"].handle(exc, context)

    # 兜底: 未知异常使用 DefaultErrorHandler
    return DefaultErrorHandler().handle(exc, context)
