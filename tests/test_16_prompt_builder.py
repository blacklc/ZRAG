"""切片 16 — PromptBuilder 测试"""
import pytest

from zrag.models.retrieval import SearchResult
from zrag.retrieval.prompt_builder import build_rag_prompt, SYSTEM_PROMPT


class TestPromptBuilder:
    """PromptBuilder 单元测试"""

    def test_build_returns_correct_structure(self):
        """返回 list[dict], 包含 system+user 两条消息"""
        results = [
            SearchResult(
                chunk_id="c1",
                content="人工智能是计算机科学的分支。",
                doc_title="AI简介",
                source_id="s1",
                source_type="markdown",
                score=0.95,
            )
        ]
        messages = build_rag_prompt("什么是人工智能？", results)

        assert isinstance(messages, list)
        assert len(messages) == 2

        assert messages[0]["role"] == "system"
        assert isinstance(messages[0]["content"], str)

        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "什么是人工智能？"

    def test_context_contains_sources(self):
        """检索结果的 doc_title 和 content 出现在 context 中"""
        results = [
            SearchResult(
                chunk_id="c1",
                content="深度学习是机器学习的一个子领域。",
                doc_title="深度学习入门",
                source_id="s1",
                source_type="markdown",
                score=0.92,
            )
        ]
        messages = build_rag_prompt("什么是深度学习？", results)
        system_content = messages[0]["content"]

        assert "[来源: 深度学习入门]" in system_content
        assert "深度学习是机器学习的一个子领域。" in system_content

    def test_empty_results(self):
        """空检索结果时 context 仅包含空字符串"""
        messages = build_rag_prompt("你好", [])
        system_content = messages[0]["content"]

        expected_system = SYSTEM_PROMPT.format(context="")
        assert system_content == expected_system

    def test_multiple_results(self):
        """多条结果用 --- 分隔"""
        results = [
            SearchResult(
                chunk_id="c1",
                content="Python 是一种高级编程语言。",
                doc_title="Python介绍",
                source_id="s1",
                source_type="markdown",
                score=0.91,
            ),
            SearchResult(
                chunk_id="c2",
                content="Java 是一种面向对象编程语言。",
                doc_title="Java介绍",
                source_id="s2",
                source_type="markdown",
                score=0.88,
            ),
            SearchResult(
                chunk_id="c3",
                content="Go 语言由 Google 设计。",
                doc_title="Go介绍",
                source_id="s3",
                source_type="markdown",
                score=0.85,
            ),
        ]
        messages = build_rag_prompt("编程语言有哪些？", results)
        system_content = messages[0]["content"]

        assert "[来源: Python介绍]" in system_content
        assert "[来源: Java介绍]" in system_content
        assert "[来源: Go介绍]" in system_content
        assert "Python 是一种高级编程语言。" in system_content
        assert "Java 是一种面向对象编程语言。" in system_content
        assert "Go 语言由 Google 设计。" in system_content

        # 验证分隔符: 三条结果应有 2 个分隔符
        assert system_content.count("---") == 2
