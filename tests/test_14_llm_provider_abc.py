"""测试切片 13 — LLMProvider ABC"""
import pytest
from zrag.llm.base import LLMProvider


class FakeProvider(LLMProvider):
    """LLMProvider 的桩实现, 用于测试具体子类可正常使用"""

    def __init__(self, responses=None):
        super().__init__(model="fake", timeout=10)
        self.responses = responses if responses is not None else ["fake response", "fake response"]
        self.call_count = 0

    def chat(self, messages):
        idx = self.call_count
        self.call_count += 1
        if idx < len(self.responses):
            return self.responses[idx]
        return None


class BrokenProvider(LLMProvider):
    """chat 方法会抛 RuntimeError 的子类, 用于测试错误处理"""

    def chat(self, messages):
        raise RuntimeError("API call failed")


class IncompleteProvider(LLMProvider):
    """未实现 chat 方法的子类, 用于测试抽象方法检查"""

    pass


class TestLLMProviderABC:
    """LLMProvider 抽象基类测试"""

    def test_cannot_instantiate_abc(self):
        """LLMProvider 是 ABC, 不能直接实例化, 应抛出 TypeError"""
        with pytest.raises(TypeError):
            LLMProvider()

    def test_concrete_provider_works(self):
        """实现全部抽象方法的子类可以实例化且方法可调用"""
        provider = FakeProvider()

        # chat() 返回预置回复
        result = provider.chat([{"role": "user", "content": "hello"}])
        assert result == "fake response"
        assert provider.call_count == 1

        # 第二次调用返回下一个预置回复
        result2 = provider.chat([{"role": "user", "content": "world"}])
        assert result2 == "fake response"
        assert provider.call_count == 2

        # 超出预置回复后返回 None
        result3 = provider.chat([{"role": "user", "content": "bye"}])
        assert result3 is None
        assert provider.call_count == 3

    def test_missing_method_raises(self):
        """未实现 chat 抽象方法的子类, 实例化时抛出 TypeError"""
        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_chat_stream_default(self):
        """chat_stream 默认实现调用 chat() 后单次 yield"""
        provider = FakeProvider(responses=["stream response"])

        results = list(provider.chat_stream([{"role": "user", "content": "hi"}]))
        assert results == ["stream response"]

    def test_chat_stream_none_result(self):
        """chat() 返回 None 时 chat_stream 不 yield 任何内容"""
        provider = FakeProvider(responses=[])

        results = list(provider.chat_stream([{"role": "user", "content": "hi"}]))
        assert results == []
