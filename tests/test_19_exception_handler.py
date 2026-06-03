"""切片 19 — BaseZragException + Handler Registry 测试"""

import pytest
from rest_framework.exceptions import AuthenticationFailed, ParseError, ValidationError
from rest_framework.response import Response

from zrag.api.exception_handler import (
    DefaultErrorHandler,
    IngestionHandler,
    LLMCallHandler,
    NotFoundHandler,
    RetrievalHandler,
    UnauthorizedHandler,
    api_exception_handler,
    error_type,
)
from zrag.api.exceptions import (
    IngestionException,
    LLMCallException,
    NotFoundException,
    RetrievalException,
    UnauthorizedException,
)
from zrag.exception.base import BaseZragException


class TestExceptionInstantiation:
    """测试 1 — 每种异常可实例化"""

    def test_unauthorized_exception(self):
        """UnauthorizedException 可正常实例化"""
        exc = UnauthorizedException()
        assert str(exc) == "Unauthorized"
        assert exc.error_code == "UNAUTHORIZED"

    def test_not_found_exception(self):
        """NotFoundException 可正常实例化"""
        exc = NotFoundException()
        assert str(exc) == "Resource not found"
        assert exc.error_code == "NOT-FOUND"

    def test_retrieval_exception(self):
        """RetrievalException 可正常实例化"""
        exc = RetrievalException("检索失败")
        assert str(exc) == "检索失败"
        assert exc.error_code == "RETRIEVAL-ERROR"

    def test_llm_call_exception(self):
        """LLMCallException 可正常实例化"""
        exc = LLMCallException("LLM 调用超时")
        assert str(exc) == "LLM 调用超时"
        assert exc.error_code == "LLM-CALL-ERROR"

    def test_ingestion_exception(self):
        """IngestionException 可正常实例化"""
        exc = IngestionException("导入失败")
        assert str(exc) == "导入失败"
        assert exc.error_code == "INGESTION-ERROR"

    def test_custom_message_and_error_code(self):
        """异常可自定义 message 和 error_code"""
        exc = NotFoundException(
            message="文档未找到", error_code="DOC-NOT-FOUND"
        )
        assert str(exc) == "文档未找到"
        assert exc.error_code == "DOC-NOT-FOUND"


class TestExceptionHttpStatus:
    """测试 2 — 状态码正确"""

    def test_unauthorized_status(self):
        """UnauthorizedException 状态码为 401"""
        exc = UnauthorizedException()
        assert exc.status_code == 401

    def test_not_found_status(self):
        """NotFoundException 状态码为 404"""
        exc = NotFoundException()
        assert exc.status_code == 404

    def test_retrieval_status(self):
        """RetrievalException 状态码为 500"""
        exc = RetrievalException("检索失败")
        assert exc.status_code == 500

    def test_llm_call_status(self):
        """LLMCallException 状态码为 502"""
        exc = LLMCallException("LLM 调用超时")
        assert exc.status_code == 502

    def test_ingestion_status(self):
        """IngestionException 状态码为 500"""
        exc = IngestionException("导入失败")
        assert exc.status_code == 500


class TestHandlerRegistry:
    """测试 3 — 注册表映射正确"""

    def test_registry_contains_all_exceptions(self):
        """注册表包含所有异常类型的映射条目"""
        registered_classes = {
            entry["exception_class"] for entry in error_type
        }
        expected = {
            UnauthorizedException,
            NotFoundException,
            RetrievalException,
            LLMCallException,
            IngestionException,
        }
        # DRF 内置异常也应在注册表中
        for drf_exc in [AuthenticationFailed, ParseError, ValidationError]:
            assert drf_exc in registered_classes, f"Missing {drf_exc}"
        assert registered_classes >= expected

    def test_registry_contains_all_handlers(self):
        """注册表包含所有处理器类型的映射条目"""
        registered_handler_classes = {
            entry["handler_class"] for entry in error_type
        }
        expected_zrag = {
            UnauthorizedHandler,
            NotFoundHandler,
            RetrievalHandler,
            LLMCallHandler,
            IngestionHandler,
        }
        assert registered_handler_classes >= expected_zrag

    def test_registry_is_sorted_by_specificity(self):
        """注册表优先级排序: 子类在前, 基类在后"""
        # BaseZragException 不应出现在注册表中
        registered_classes = {
            entry["exception_class"] for entry in error_type
        }
        assert BaseZragException not in registered_classes


class TestHandlerReturnsResponse:
    """测试 4 — handler 返回 Response 对象"""

    def test_unauthorized_handler(self):
        """UnauthorizedHandler 返回 401 Response"""
        exc = UnauthorizedException()
        context = {}
        handler = UnauthorizedHandler()
        response = handler.handle(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 401

    def test_not_found_handler(self):
        """NotFoundHandler 返回 404 Response"""
        exc = NotFoundException()
        context = {}
        handler = NotFoundHandler()
        response = handler.handle(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 404

    def test_retrieval_handler(self):
        """RetrievalHandler 返回 500 Response"""
        exc = RetrievalException("检索失败")
        context = {}
        handler = RetrievalHandler()
        response = handler.handle(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 500

    def test_llm_call_handler(self):
        """LLMCallHandler 返回 502 Response"""
        exc = LLMCallException("LLM 调用超时")
        context = {}
        handler = LLMCallHandler()
        response = handler.handle(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 502

    def test_ingestion_handler(self):
        """IngestionHandler 返回 500 Response"""
        exc = IngestionException("导入失败")
        context = {}
        handler = IngestionHandler()
        response = handler.handle(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 500

    def test_response_contains_error_code(self):
        """Response 数据中包含 ErrorCode 字段"""
        exc = NotFoundException(message="文档未找到", error_code="DOC-NOT-FOUND")
        context = {}
        handler = NotFoundHandler()
        response = handler.handle(exc, context)
        assert response.data["ErrorCode"] == "DOC-NOT-FOUND"
        assert response.data["Message"] == "文档未找到"

    def test_api_exception_handler_returns_response(self):
        """api_exception_handler 入口函数返回 Response"""
        exc = UnauthorizedException()
        context = {}
        response = api_exception_handler(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 401


class TestDefaultHandler:
    """测试 5 — 未知异常走兜底"""

    def test_default_handler_for_unknown_exception(self):
        """未知异常使用 DefaultErrorHandler 返回 500"""
        exc = ValueError("未知错误")
        context = {}
        response = api_exception_handler(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 500
        assert response.data["Message"] == "Internal server error"
        assert response.data["ErrorCode"] == "INTERNAL-ERROR"

    def test_default_handler_direct_call(self):
        """DefaultErrorHandler 直接调用返回 500"""
        exc = RuntimeError("运行时错误")
        context = {}
        handler = DefaultErrorHandler()
        response = handler.handle(exc, context)
        assert isinstance(response, Response)
        assert response.status_code == 500
