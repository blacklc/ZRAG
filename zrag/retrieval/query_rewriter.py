"""查询改写器模块

使用 LLM 将用户口语化查询改写为结构化搜索表达，
产出关键词列表（用于 FTS5 全文检索）和精炼查询（用于向量语义检索）。
"""

import json
import logging
import os

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class QueryRewriter:
    """查询改写器

    使用 LLM 将用户口语化查询改写为结构化搜索表达，
    产出关键词列表（用于 FTS5 全文检索）和精炼查询（用于向量语义检索）。

    @param llm_provider: LLM Provider 实例（需实现 chat() 方法）
    @type  llm_provider: object
    @param prompts_dir: Jinja2 模板目录路径，默认为 prompts/ 目录
    @type  prompts_dir: str, optional
    """

    def __init__(self, llm_provider, prompts_dir: str = None):
        """初始化查询改写器

        @param llm_provider: LLM Provider 实例（需实现 chat() 方法）
        @type  llm_provider: object
        @param prompts_dir: Jinja2 模板目录路径，默认为 prompts/ 目录
        @type  prompts_dir: str, optional
        """
        self._llm = llm_provider

        # 加载 Jinja2 模板
        if prompts_dir is None:
            prompts_dir = os.path.join(
                os.path.dirname(__file__), '..', 'prompts'
            )
        self._env = Environment(loader=FileSystemLoader(prompts_dir))
        self._template = self._env.get_template('query_rewrite.j2')

    def rewrite(self, query: str) -> dict:
        """改写用户查询

        @param query: 用户原始查询
        @type  query: str

        @return: {"keywords": "...", "refined_query": "..."}
                 解析失败时降级返回 {"keywords": query, "refined_query": query}
        @rtype:  dict
        """
        prompt = self._template.render(query=query)
        messages = [{"role": "system", "content": prompt}]

        try:
            response = self._llm.chat(messages)
            if response is None:
                logger.warning(
                    "LLM chat returned None, falling back to original query"
                )
                return {"keywords": query, "refined_query": query}
            return self._parse_response(response, query)
        except Exception as e:
            logger.warning(
                "Query rewriting failed: %s, falling back to original query", e
            )
            return {"keywords": query, "refined_query": query}

    def _parse_response(self, response: str, query: str) -> dict:
        """解析 LLM 返回的 JSON

        处理 LLM 可能包裹 markdown 代码块的情况。
        解析失败时降级返回原始查询。

        @param response: LLM 原始响应文本
        @type  response: str
        @param query: 原始查询（用于降级回退）
        @type  query: str

        @return: {"keywords": "...", "refined_query": "..."}
        @rtype:  dict
        """
        text = response.strip()

        # 尝试移除 markdown 代码块包裹
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首行 ```json 或 ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 去掉末行 ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            result = json.loads(text)
            return {
                "keywords": result.get("keywords", query),
                "refined_query": result.get("refined_query", query),
            }
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse JSON from LLM response: %s", text[:200]
            )
            return {"keywords": query, "refined_query": query}
