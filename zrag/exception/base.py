"""ZRAG 全局异常基类"""


class BaseZragException(Exception):
    """ZRAG 全局异常基类

    所有 ZRAG 内部自定义异常的基类。
    子类可通过重写 status_code 属性提供对应的 HTTP 状态码。

    错误处理策略：
      - LLMProvider 在未提供 on_error 回调时抛出此异常
      - 具体的异常子类（如 LLMCallException）应继承此基类
      - API 层的异常子类通过 error_code 属性提供业务错误码

    @param message: 可选的错误描述信息, defaults to ""
    @type  message: str, optional
    @param status_code: HTTP 状态码, defaults to 500
    @type  status_code: int, optional
    @param http_status: HTTP 状态码别名, 优先级高于 status_code, defaults to None
    @type  http_status: int, optional
    @param error_code: 业务错误码, defaults to ""
    @type  error_code: str, optional
    """

    def __init__(
        self,
        message: str = "",
        status_code: int = 500,
        http_status: int = None,
        error_code: str = "",
    ):
        """构造 BaseZragException

        @param message: 错误描述信息, defaults to ""
        @type  message: str, optional
        @param status_code: HTTP 状态码, defaults to 500
        @type  status_code: int, optional
        @param http_status: HTTP 状态码别名, 优先级高于 status_code, defaults to None
        @type  http_status: int, optional
        @param error_code: 业务错误码, defaults to ""
        @type  error_code: str, optional
        """
        super().__init__(message)
        if http_status is not None:
            status_code = http_status
        self.status_code = status_code
        self.error_code = error_code
