"""API 异常体系

定义 ZRAG API 层使用的各类业务异常。
所有异常继承 zrag.exception.base.BaseZragException。
"""

from zrag.exception.base import BaseZragException


class UnauthorizedException(BaseZragException):
    """未授权异常

    当请求缺少有效身份认证信息时抛出。

    @param message: 错误描述信息, defaults to "Unauthorized"
    @type  message: str, optional
    @param error_code: 业务错误码, defaults to "UNAUTHORIZED"
    @type  error_code: str, optional
    """

    def __init__(self, message="Unauthorized", error_code="UNAUTHORIZED"):
        """构造 UnauthorizedException

        @param message: 错误描述信息, defaults to "Unauthorized"
        @type  message: str, optional
        @param error_code: 业务错误码, defaults to "UNAUTHORIZED"
        @type  error_code: str, optional
        """
        super().__init__(http_status=401, message=message, error_code=error_code)


class NotFoundException(BaseZragException):
    """资源未找到异常

    当请求的资源不存在时抛出。

    @param message: 错误描述信息, defaults to "Resource not found"
    @type  message: str, optional
    @param error_code: 业务错误码, defaults to "NOT-FOUND"
    @type  error_code: str, optional
    """

    def __init__(self, message="Resource not found", error_code="NOT-FOUND"):
        """构造 NotFoundException

        @param message: 错误描述信息, defaults to "Resource not found"
        @type  message: str, optional
        @param error_code: 业务错误码, defaults to "NOT-FOUND"
        @type  error_code: str, optional
        """
        super().__init__(http_status=404, message=message, error_code=error_code)


class RetrievalException(BaseZragException):
    """检索异常

    当检索过程中发生错误时抛出。

    @param message: 错误描述信息
    @type  message: str
    @param error_code: 业务错误码, defaults to "RETRIEVAL-ERROR"
    @type  error_code: str, optional
    """

    def __init__(self, message, error_code="RETRIEVAL-ERROR"):
        """构造 RetrievalException

        @param message: 错误描述信息
        @type  message: str
        @param error_code: 业务错误码, defaults to "RETRIEVAL-ERROR"
        @type  error_code: str, optional
        """
        super().__init__(http_status=500, message=message, error_code=error_code)


class LLMCallException(BaseZragException):
    """LLM 调用异常

    当 LLM 调用过程中发生错误时抛出。

    @param message: 错误描述信息
    @type  message: str
    @param error_code: 业务错误码, defaults to "LLM-CALL-ERROR"
    @type  error_code: str, optional
    """

    def __init__(self, message, error_code="LLM-CALL-ERROR"):
        """构造 LLMCallException

        @param message: 错误描述信息
        @type  message: str
        @param error_code: 业务错误码, defaults to "LLM-CALL-ERROR"
        @type  error_code: str, optional
        """
        super().__init__(http_status=502, message=message, error_code=error_code)


class IngestionException(BaseZragException):
    """数据导入异常

    当数据导入过程中发生错误时抛出。

    @param message: 错误描述信息
    @type  message: str
    @param error_code: 业务错误码, defaults to "INGESTION-ERROR"
    @type  error_code: str, optional
    """

    def __init__(self, message, error_code="INGESTION-ERROR"):
        """构造 IngestionException

        @param message: 错误描述信息
        @type  message: str
        @param error_code: 业务错误码, defaults to "INGESTION-ERROR"
        @type  error_code: str, optional
        """
        super().__init__(http_status=500, message=message, error_code=error_code)
