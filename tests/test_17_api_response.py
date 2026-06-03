"""测试切片 17 — APIResponse 包装器"""
import json

from django.test.client import RequestFactory
from rest_framework.renderers import JSONRenderer

from zrag.api import APIResponse


class TestAPIResponse:
    """APIResponse 统一响应格式测试"""

    def test_success_response(self):
        """200 成功响应包含 Message/Data/RequestID 结构"""
        response = APIResponse(data={"key": "value"}, message="success")
        assert response.status_code == 200
        assert response.data["Message"] == "success"
        assert response.data["Data"] == {"key": "value"}
        assert "RequestID" in response.data

    def test_error_response(self):
        """非 200 状态码的错误响应"""
        response = APIResponse(
            data=None,
            message="not found",
            http_status=404,
        )
        assert response.status_code == 404
        assert response.data["Message"] == "not found"
        assert response.data["Data"] is None
        assert "RequestID" in response.data

    def test_request_id_from_header(self):
        """X-Request-ID 请求头会被正确提取到响应中"""
        factory = RequestFactory()
        request = factory.get("/fake", HTTP_X_REQUEST_ID="uuid-12345")
        response = APIResponse(data={"result": "ok"}, request=request)
        assert response.data["RequestID"] == "uuid-12345"

    def test_request_id_missing(self):
        """未提供 X-Request-ID 时 RequestID 为空字符串"""
        factory = RequestFactory()
        request = factory.get("/fake")
        response = APIResponse(data={"result": "ok"}, request=request)
        assert response.data["RequestID"] == ""

    def test_response_serialization(self):
        """JSON 序列化后包含正确的字段"""
        factory = RequestFactory()
        request = factory.get("/fake", HTTP_X_REQUEST_ID="req-999")
        response = APIResponse(
            data={"items": [1, 2, 3]},
            message="ok",
            request=request,
        )
        # 手动设置 renderer 并调用 render() 完成序列化
        response.accepted_renderer = JSONRenderer()
        response.accepted_media_type = "application/json"
        response.renderer_context = {}
        response.render()
        body = json.loads(response.content)
        assert body["Message"] == "ok"
        assert body["Data"] == {"items": [1, 2, 3]}
        assert body["RequestID"] == "req-999"
