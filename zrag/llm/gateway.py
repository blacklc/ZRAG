"""LiteLLM Gateway LLM 实现

通过 OpenAI SDK 连接自托管的 LiteLLM Gateway，
支持 smart-router 负载均衡和多种模型切换。
"""
import os
from typing import Callable, Iterator

from openai import OpenAI

from zrag.api.exceptions import LLMCallException
from zrag.ingest.pipeline import ErrorEvent
from zrag.llm.base import LLMProvider


class LLMGatewayProvider(LLMProvider):
    """LiteLLM Gateway LLM 实现

    使用 OpenAI SDK 连接自托管的 LiteLLM Gateway。
    支持 smart-router 负载均衡和多种模型切换。

    @param model: 模型名称, defaults to "smart-router"
    @type  model: str, optional
    @param timeout: 请求超时秒数, defaults to 200
    @type  timeout: float, optional
    @param base_url: LiteLLM Gateway 地址, defaults to "http://localhost:4000/v1"
    @type  base_url: str, optional
    @param on_error: 错误回调函数, 接收 ErrorEvent
    @type  on_error: callable, optional
    """

    def __init__(
        self,
        model: str = "smart-router",
        timeout: float = 200,
        base_url: str | None = None,
        on_error: Callable | None = None,
    ):
        """构造 LLMGatewayProvider

        @param model: 模型名称, defaults to "smart-router"
        @type  model: str, optional
        @param timeout: 请求超时秒数, defaults to 200
        @type  timeout: float, optional
        @param base_url: LiteLLM Gateway 地址, defaults to "http://localhost:4000/v1"
        @type  base_url: str, optional
        @param on_error: 错误回调函数, 接收 ErrorEvent
        @type  on_error: callable, optional
        """
        super().__init__(model=model, timeout=timeout, on_error=on_error)
        gateway_url = base_url or os.environ.get(
            "LLM_GATEWAY_URL", "http://localhost:4000/v1"
        )
        self.client = OpenAI(
            base_url=gateway_url,
            api_key=os.environ.get("LITELLM_MASTER_KEY", "sk-dummy"),
        )

    def chat(self, messages: list[dict], timeout: float | None = None) -> str | None:
        """同步非流式对话

        通过 OpenAI SDK 调用 LiteLLM Gateway。

        @param messages: 消息列表
        @type  messages: list[dict]
        @param timeout: 超时覆盖, defaults to None（使用构造时的超时）
        @type  timeout: float, optional

        @return: 模型回复文本; 失败且 on_error 已提供时返回 None
        @type:   str | None

        @raises: on_error 未提供时抛 LLMCallException
        @type:   LLMCallException
        """
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,
                timeout=timeout or self.timeout,
            )
            return resp.choices[0].message.content
        except Exception as e:
            if self._on_error:
                self._on_error(ErrorEvent(
                    source_id="llm_gateway",
                    error=f"LLM call failed: {e}",
                    exception=e,
                ))
                return None
            raise LLMCallException(str(e))

    def chat_stream(
        self, messages: list[dict], timeout: float | None = None
    ) -> Iterator[str]:
        """流式对话

        Phase 2 实现真正的 SSE 流式。

        @param messages: 消息列表
        @type  messages: list[dict]

        @return: 生成器, 逐 token yield
        @type:   Iterator[str]
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,
                stream=True,
                timeout=timeout or self.timeout,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            if self._on_error:
                self._on_error(ErrorEvent(
                    source_id="llm_gateway",
                    error=f"LLM stream failed: {e}",
                    exception=e,
                ))
            else:
                raise LLMCallException(str(e))
