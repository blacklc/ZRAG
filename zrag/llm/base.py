"""LLM 调用抽象基类"""
from abc import ABC, abstractmethod
from typing import Callable, Iterator

from zrag.exception.base import BaseZragException


class LLMProvider(ABC):
    """LLM 调用抽象基类

    定义与大语言模型通信的统一接口。
    所有具体的 LLM Provider 实现必须继承此类并实现全部抽象方法。

    chat() 用于同步非流式对话, chat_stream() 用于流式对话。

    on_error 回调策略:
      - 回调函数已提供 -> 通知回调, 不抛异常 (chat 返回 None, chat_stream 生成器空)
      - 回调函数未提供 -> 抛 BaseZragException

    @param model: 模型名称, defaults to None
    @type  model: str, optional
    @param timeout: 请求超时时间(秒), defaults to 200
    @type  timeout: float, optional
    @param on_error: 错误回调函数, 接收 ErrorEvent, defaults to None
    @type  on_error: callable, optional
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: float | None = None,
        on_error: Callable | None = None,
    ):
        """构造 LLMProvider

        若 model 或 timeout 未显式传入，则从 Django settings.ZRAG_LLM 配置中读取。
        配置中也缺失时抛出 ValueError。

        @param model: 模型名称, 未传入则从配置读取, defaults to None
        @type  model: str, optional
        @param timeout: 请求超时时间(秒), 未传入则从配置读取, defaults to None
        @type  timeout: float, optional
        @param on_error: 错误回调函数, 接收 ErrorEvent, defaults to None
        @type  on_error: callable, optional

        @raises ValueError: model 或 timeout 在参数和配置中均未提供时抛出
        """
        from django.conf import settings
        llm_cfg = getattr(settings, "ZRAG_LLM", {})
        self._model = model if model is not None else llm_cfg.get("gateway", {}).get("model")
        if not self._model:
            raise ValueError("配置缺失: llm.gateway.model")
        self._timeout = timeout if timeout is not None else llm_cfg.get("timeout")
        if self._timeout is None:
            raise ValueError("配置缺失: llm.timeout")
        self._on_error = on_error

    @property
    def model(self) -> str | None:
        """获取模型名称

        @return: 模型名称
        @type:   str | None
        """
        return self._model

    @property
    def timeout(self) -> float:
        """获取请求超时时间

        @return: 超时时间(秒)
        @type:   float
        """
        return self._timeout

    @abstractmethod
    def chat(self, messages: list[dict]) -> str | None:
        """同步非流式对话

        @param messages: 消息列表, 格式为 [{"role": "user", "content": "..."}]
        @type  messages: list[dict]

        @return: 模型回复文本; 若发生错误且 on_error 已提供则返回 None
        @type:   str | None

        @raises: 当 on_error 未提供且调用失败时抛出
        @type:   BaseZragException
        """
        ...

    def chat_stream(self, messages: list[dict]) -> Iterator[str]:
        """流式对话

        Phase 1 默认实现: 调用 chat() 后将结果作为单次 yield 返回。
        子类在 Phase 2 可 override 实现真正的流式输出。

        @param messages: 消息列表
        @type  messages: list[dict]

        @return: 生成器, 逐 token yield 回复文本
        @type:   Iterator[str]
        """
        result = self.chat(messages)
        if result is not None:
            yield result

    def _retry(self, func, *args, **kwargs):
        """重试机制预留方法

        子类可 override 实现指数退避重试逻辑。
        Phase 1 暂不实现具体重试逻辑。

        @param func: 需要重试的可调用对象
        @type  func: callable
        @param *args: 传递给 func 的位置参数
        @param **kwargs: 传递给 func 的关键字参数

        @return: func 的执行结果
        """
        return func(*args, **kwargs)
