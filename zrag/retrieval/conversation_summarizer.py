import logging
import os
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """对话摘要压缩器

    将多轮对话内容压缩为简洁的自然语言摘要，用于注入查询改写阶段。
    采用增量压缩策略：每次传入已有摘要 + 最新一轮 Q&A，生成更新后的摘要。
    """

    def __init__(self, llm_provider):
        """初始化 ConversationSummarizer

        @param llm_provider: LLMProvider 实例，需实现 chat(messages) -> str | None
        @type  llm_provider: object
        """
        self._llm = llm_provider
        template_dir = str(
            Path(__file__).resolve().parent.parent / "prompts"
        )
        self._env = Environment(loader=FileSystemLoader(template_dir))
        self._template = self._env.get_template("compress.j2")

    _FIXED_OVERHEAD_TOKENS = 600  # system_prompt + old_summary + 输出预留

    @staticmethod
    def _truncate_by_chars(text: str, token_budget: int) -> str:
        """按 token 预算截断文本（中文约 1.5 字符/token）

        @param text:         待截断文本
        @type  text: str
        @param token_budget: token 预算上限
        @type  token_budget: int

        @return: 截断后的文本
        @rtype:  str
        """
        max_len = int(token_budget * 1.5)
        return text[:max_len]

    def summarize(self, old_summary: str, user_query: str, assistant_reply: str,
                  max_chars: int = 200, context_window: int = 32768) -> str:
        """生成更新后的对话摘要

        @param old_summary:     已有摘要（空字符串表示首轮对话）
        @type  old_summary: str
        @param user_query:      本轮用户查询文本
        @type  user_query: str
        @param assistant_reply: 本轮助手回复文本
        @type  assistant_reply: str
        @param max_chars:       摘要最大长度（字），默认 200
        @type  max_chars: int, optional
        @param context_window:  模型上下文窗口大小，默认 32768
        @type  context_window: int, optional

        @return: 更新后的摘要文本；失败时返回空字符串
        @rtype:  str
        """
        logger.info(
            "summarize entry",
            extra={"old_summary_len": len(old_summary), "query_len": len(user_query), "reply_len": len(assistant_reply)},
        )

        available = context_window - self._FIXED_OVERHEAD_TOKENS
        query_budget = available // 4    # user_query 保留 1/4
        reply_budget = available - query_budget  # assistant_reply 占 3/4

        truncated_query = self._truncate_by_chars(user_query, query_budget)
        truncated_reply = self._truncate_by_chars(assistant_reply, reply_budget)

        messages = self._render_messages(old_summary, truncated_query, truncated_reply, max_chars=max_chars)
        raw_text = self._call_llm(messages)
        if not raw_text:
            logger.warning("LLM 返回空结果，跳过摘要更新")
            return ""

        cleaned = self._clean_summary(raw_text, max_chars=max_chars)
        if not cleaned:
            return ""

        logger.info(
            "summarize success",
            extra={"new_summary_len": len(cleaned)},
        )
        return cleaned

    def _render_messages(self, old_summary: str, user_query: str, truncated_reply: str, max_chars: int = 200) -> list[dict]:
        """渲染 system + user 消息

        @param old_summary:     已有摘要
        @type  old_summary: str
        @param user_query:      本轮用户查询
        @type  user_query: str
        @param truncated_reply: 截断后的本轮助手回复
        @type  truncated_reply: str
        @param max_chars:       摘要最大长度（字），默认 200
        @type  max_chars: int, optional

        @return: 包含 system 和 user 两条消息的列表
        @rtype:  list[dict]
        """
        system_prompt = self._template.render(max_chars=max_chars)
        summary_part = old_summary if old_summary else "（首轮对话，无已有摘要）"
        user_content = (
            f"已有摘要：{summary_part}\n\n"
            f"最新一轮对话：\n"
            f"用户提问：{user_query}\n"
            f"助手回答：{truncated_reply}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _call_llm(self, messages: list[dict]) -> str:
        """调用 LLM，返回响应文本

        @param messages: 消息列表
        @type  messages: list[dict]

        @return: LLM 返回的文本，失败时返回空字符串
        @rtype:  str
        """
        try:
            response = self._llm.chat(messages)
            if response is None:
                return ""
            return response
        except Exception as e:
            logger.warning("ConversationSummarizer LLM 调用失败", extra={"error": str(e)})
            return ""

    def _clean_summary(self, raw_text: str, max_chars: int = 200) -> str:
        """清理 LLM 输出的废话前缀，截断到 max_chars

        @param raw_text: LLM 原始输出文本
        @type  raw_text: str
        @param max_chars: 摘要最大长度（字），默认 200
        @type  max_chars: int, optional

        @return: 清理后的摘要文本
        @rtype:  str
        """
        text = raw_text.strip()

        # 匹配并移除前缀（支持全角 ：和半角 :）
        prefixes = [
            "好的，",
            "好的,",
            "以下是",
            "更新后的摘要：",
            "更新后的摘要:",
            "摘要：",
            "摘要:",
            "总结：",
            "总结:",
            "：",
            ":",
        ]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        # 截断到 max_chars
        text = text[:max_chars]
        return text
