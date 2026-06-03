"""测试切片 14 — LLMGatewayProvider"""
import pytest
from unittest.mock import patch, MagicMock

from zrag.api.exceptions import LLMCallException
from zrag.ingest.pipeline import ErrorEvent
from zrag.llm.gateway import LLMGatewayProvider


class TestLLMGatewayProvider:
    """LLMGatewayProvider 单元测试

    通过 mock OpenAI SDK 来验证 LLMGatewayProvider 的行为,
    不依赖真实的 LiteLLM Gateway 服务。
    """

    @patch("zrag.llm.gateway.OpenAI")
    def test_chat_success(self, mock_openai):
        """mock SDK 返回正常回复, chat() 应返回字符串"""
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Hello from LLM"
        mock_instance.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_instance

        provider = LLMGatewayProvider(model="test-model", timeout=30)
        result = provider.chat([{"role": "user", "content": "hi"}])

        assert result == "Hello from LLM"
        mock_instance.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.4,
            timeout=30,
        )

    @patch("zrag.llm.gateway.OpenAI")
    def test_chat_with_on_error(self, mock_openai):
        """SDK 抛异常且 on_error 已提供, chat() 应返回 None, 回调被调用"""
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.side_effect = RuntimeError("API error")
        mock_openai.return_value = mock_instance

        on_error_callback = MagicMock()
        provider = LLMGatewayProvider(
            model="test-model", timeout=10, on_error=on_error_callback
        )
        result = provider.chat([{"role": "user", "content": "hi"}])

        assert result is None
        on_error_callback.assert_called_once()
        event = on_error_callback.call_args[0][0]
        assert isinstance(event, ErrorEvent)
        assert event.source_id == "llm_gateway"
        assert "API error" in event.error
        assert isinstance(event.exception, RuntimeError)

    @patch("zrag.llm.gateway.OpenAI")
    def test_chat_without_on_error(self, mock_openai):
        """SDK 抛异常且无回调, chat() 应抛 LLMCallException"""
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.side_effect = RuntimeError("API error")
        mock_openai.return_value = mock_instance

        provider = LLMGatewayProvider(model="test-model", timeout=10)
        with pytest.raises(LLMCallException) as exc_info:
            provider.chat([{"role": "user", "content": "hi"}])

        assert "API error" in str(exc_info.value)

    @patch("zrag.llm.gateway.OpenAI")
    def test_chat_stream(self, mock_openai):
        """mock 流式返回, chat_stream() 应 yield 正确 token"""
        mock_instance = MagicMock()
        mock_chunk_1 = MagicMock()
        mock_chunk_1.choices = [MagicMock()]
        mock_chunk_1.choices[0].delta.content = "Hello"
        mock_chunk_2 = MagicMock()
        mock_chunk_2.choices = [MagicMock()]
        mock_chunk_2.choices[0].delta.content = " world"
        mock_chunk_3 = MagicMock()
        mock_chunk_3.choices = [MagicMock()]
        mock_chunk_3.choices[0].delta.content = None

        mock_instance.chat.completions.create.return_value = [
            mock_chunk_1,
            mock_chunk_2,
            mock_chunk_3,
        ]
        mock_openai.return_value = mock_instance

        provider = LLMGatewayProvider(model="test-model", timeout=10)
        result = list(provider.chat_stream([{"role": "user", "content": "hi"}]))

        assert result == ["Hello", " world"]
        mock_instance.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.4,
            stream=True,
            timeout=10,
        )

    @patch("zrag.llm.gateway.OpenAI")
    def test_chat_stream_error_with_callback(self, mock_openai):
        """流式异常, on_error 回调被调用"""
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.side_effect = ConnectionError("connection lost")
        mock_openai.return_value = mock_instance

        on_error_callback = MagicMock()
        provider = LLMGatewayProvider(
            model="test-model", timeout=10, on_error=on_error_callback
        )

        gen = provider.chat_stream([{"role": "user", "content": "hi"}])
        # 生成器不应 yield 任何结果, 且应调用回调
        results = list(gen)
        assert results == []

        on_error_callback.assert_called_once()
        event = on_error_callback.call_args[0][0]
        assert isinstance(event, ErrorEvent)
        assert event.source_id == "llm_gateway"
        assert "stream failed" in event.error

    @patch("zrag.llm.gateway.OpenAI")
    def test_chat_stream_error_without_callback(self, mock_openai):
        """流式异常, 无 on_error 回调, 应抛 LLMCallException"""
        mock_instance = MagicMock()
        mock_instance.chat.completions.create.side_effect = ConnectionError("connection lost")
        mock_openai.return_value = mock_instance

        provider = LLMGatewayProvider(model="test-model", timeout=10)

        gen = provider.chat_stream([{"role": "user", "content": "hi"}])
        with pytest.raises(LLMCallException) as exc_info:
            list(gen)

        assert "connection lost" in str(exc_info.value)
