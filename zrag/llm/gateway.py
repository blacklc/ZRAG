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
        model: str | None = None,
        timeout: float | None = None,
        base_url: str | None = None,
        on_error: Callable | None = None,
    ):
        """构造 LLMGatewayProvider

        若 model、timeout 或 base_url 未显式传入，则从 Django settings.ZRAG_LLM 配置中读取。
        配置中也缺失时抛出 ValueError。

        @param model: 模型名称, 未传入则从配置读取, defaults to None
        @type  model: str, optional
        @param timeout: 请求超时秒数, 未传入则从配置读取, defaults to None
        @type  timeout: float, optional
        @param base_url: LiteLLM Gateway 地址, 未传入则从配置读取, defaults to None
        @type  base_url: str, optional
        @param on_error: 错误回调函数, 接收 ErrorEvent
        @type  on_error: callable, optional

        @raises ValueError: 必要配置项在参数和配置中均未提供时抛出
        """
        from django.conf import settings
        llm_cfg = getattr(settings, "ZRAG_LLM", {})
        gateway_cfg = llm_cfg.get("gateway", {})

        self._model = model if model is not None else gateway_cfg.get("model")
        if not self._model:
            raise ValueError("配置缺失: llm.gateway.model, 请检查 config/llm.yaml")

        self._timeout = timeout if timeout is not None else llm_cfg.get("timeout")
        if self._timeout is None:
            raise ValueError("配置缺失: llm.timeout, 请检查 config/llm.yaml")

        base_url_val = base_url if base_url is not None else gateway_cfg.get("base_url")
        if not base_url_val:
            raise ValueError("配置缺失: llm.gateway.base_url, 请检查 config/llm.yaml")

        api_key_val = gateway_cfg.get("api_key")
        if not api_key_val:
            raise ValueError("配置缺失: llm.gateway.api_key, 请检查 config/llm.yaml 或设置 LITELLM_MASTER_KEY")

        super().__init__(model=self._model, timeout=self._timeout, on_error=on_error)
        self.client = OpenAI(base_url=base_url_val, api_key=api_key_val)

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
