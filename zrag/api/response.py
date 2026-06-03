"""API 响应包装器

提供统一的 API 响应格式封装, 基于 Django REST Framework 的 Response 类实现。
"""

from rest_framework.response import Response


class APIResponse(Response):
    """自定义 DRF Response 包装器

    统一 API 响应格式:
    {
        "Message": "success" | error_description,
        "Data": { ... } 或 None,
        "RequestID": "uuid"
    }

    自动从 request.META["X-Request-ID"] 读取 RequestID。

    @param data: 响应数据, defaults to None
    @type  data: any, optional
    @param message: 响应消息, defaults to "success"
    @type  message: str, optional
    @param http_status: HTTP 状态码, defaults to 200
    @type  http_status: int, optional
    @param request: Django 请求对象, 用于提取 RequestID, defaults to None
    @type  request: django.http.HttpRequest, optional

    @return: 无直接返回值, 通过 super().__init__ 构造 Response 对象
    @rtype:  rest_framework.response.Response
    """

    def __init__(self, data=None, message="success", http_status=200, request=None):
        """构造 APIResponse

        @param data: 响应数据, defaults to None
        @type  data: any, optional
        @param message: 响应消息, defaults to "success"
        @type  message: str, optional
        @param http_status: HTTP 状态码, defaults to 200
        @type  http_status: int, optional
        @param request: Django 请求对象, 用于提取 RequestID, defaults to None
        @type  request: django.http.HttpRequest, optional
        """
        request_id = ""
        if request:
            # 优先读取 WSGI 风格 (HTTP_X_REQUEST_ID), 再尝试原生 META 键 (X-Request-ID)
            request_id = request.META.get("HTTP_X_REQUEST_ID", "")
            if not request_id:
                request_id = request.META.get("X-Request-ID", "")
        body = {"Message": message, "Data": data, "RequestID": request_id}
        super().__init__(body, status=http_status)
