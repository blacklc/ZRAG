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

    _MAX_REPLY_CHARS = 500  # 助手回复截断长度

    def __init__(self, llm_provider, template_dir=None, max_chars=200):
        """初始化 ConversationSummarizer

        @param llm_provider: LLMProvider 实例，需实现 chat(messages) -> str | None
        @type  llm_provider: object
        @param template_dir: Prompt 模板目录路径，默认从 zrag/prompts 读取
        @type  template_dir: str, optional
        @param max_chars:    摘要最大长度（字），默认 200
        @type  max_chars: int, optional
        """
        self._llm = llm_provider
        self._max_chars = max_chars

        if template_dir is None:
            template_dir = str(
                Path(__file__).resolve().parent.parent / "prompts"
            )
        self._env = Environment(loader=FileSystemLoader(template_dir))
        self._template = self._env.get_template("compress.j2")

    def summarize(self, old_summary: str, user_query: str, assistant_reply: str) -> str:
        """生成更新后的对话摘要

        @param old_summary:     已有摘要（空字符串表示首轮对话）
        @type  old_summary: str
        @param user_query:      本轮用户查询文本
        @type  user_query: str
        @param assistant_reply: 本轮助手回复文本（内部截断到 _MAX_REPLY_CHARS）
        @type  assistant_reply: str

        @return: 更新后的摘要文本；失败时返回空字符串
        @rtype:  str
        """
        logger.info(
            "summarize entry: old_summary_len=%d query_len=%d reply_len=%d",
            len(old_summary), len(user_query), len(assistant_reply),
        )

        truncated_reply = assistant_reply[:self._MAX_REPLY_CHARS]
        messages = self._render_messages(old_summary, user_query, truncated_reply)
        raw_text = self._call_llm(messages)
        if not raw_text:
            logger.warning("LLM 返回空结果，跳过摘要更新")
            return ""

        cleaned = self._clean_summary(raw_text)
        if not cleaned:
            return ""

        logger.info(
            "summarize success: new_summary_len=%d max_chars=%d",
            len(cleaned), self._max_chars,
        )
        return cleaned

    def _render_messages(self, old_summary: str, user_query: str, truncated_reply: str) -> list[dict]:
        """渲染 system + user 消息

        @param old_summary:     已有摘要
        @type  old_summary: str
        @param user_query:      本轮用户查询
        @type  user_query: str
        @param truncated_reply: 截断后的本轮助手回复
        @type  truncated_reply: str

        @return: 包含 system 和 user 两条消息的列表
        @rtype:  list[dict]
        """
        system_prompt = self._template.render(max_chars=self._max_chars)
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
            logger.warning("ConversationSummarizer LLM call failed: %s", e)
            return ""

    def _clean_summary(self, raw_text: str) -> str:
        """清理 LLM 输出的废话前缀，截断到 max_chars

        @param raw_text: LLM 原始输出文本
        @type  raw_text: str

        @return: 清理后的摘要文本
        @rtype:  str
        """
        text = raw_text.strip()

        # 匹配并移除前缀（支持全角 ：和半角 :）
        prefixes = [
            r"好的，",
            r"好的,",
            r"以下是",
            r"更新后的摘要：",
            r"更新后的摘要:",
            r"摘要：",
            r"摘要:",
            r"总结：",
            r"总结:",
            r"：",
            r":",
        ]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        # 截断到 max_chars
        text = text[:self._max_chars]
        return text
