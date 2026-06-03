import uuid


class RequestIDMiddleware:
    """为每个请求自动生成/透传 X-Request-ID

    若请求头已包含 X-Request-ID 则沿用, 否则自动生成 UUID。
    将 request_id 注入到 request.META 中供 APIResponse 使用。

    @param get_response: Django 中间件链中的下一个可调用对象
    @type  get_response: callable
    """

    def __init__(self, get_response):
        """构造方法

        @param get_response: Django 中间件链中的下一个可调用对象
        @type  get_response: callable
        """
        self.get_response = get_response

    def __call__(self, request):
        """处理每个请求

        从请求头中获取 X-Request-ID, 若不存在则自动生成 UUID。
        将 request_id 注入到 request.META 和响应头中。

        @param request: Django 请求对象
        @type  request: django.http.HttpRequest

        @return: 带有 X-Request-ID 响应头的响应对象
        @rtype:  django.http.HttpResponse
        """
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.META["X-Request-ID"] = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response
