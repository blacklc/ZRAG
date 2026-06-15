"""切片 106a3: QueryRewriter 单元测试

测试 QueryRewriter 的 rewrite 方法, 包括:
- 正常 JSON 解析
- Markdown 代码块包裹的 JSON
- 非法 JSON 降级
- LLM 异常降级
- JSON 缺少字段
- 空查询
"""

import json
import os
import tempfile

from unittest.mock import MagicMock

import pytest

from zrag.retrieval.query_rewriter import QueryRewriter


class TestQueryRewriter:
    """QueryRewriter 单元测试"""

    @pytest.fixture
    def prompts_dir(self):
        """创建临时 prompts 目录, 内含最小化 query_rewrite.j2 模板

        @yield: 临时目录路径
        @rtype: str
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = os.path.join(tmpdir, 'query_rewrite.j2')
            with open(template_path, 'w') as f:
                f.write("{{ query }}")
            yield tmpdir

    @pytest.fixture
    def llm_provider(self):
        """创建 Mock LLM Provider (提供 chat() 方法)

        @return: MagicMock 实例
        @rtype: MagicMock
        """
        return MagicMock()

    @pytest.fixture
    def rewriter(self, llm_provider, prompts_dir):
        """构造 QueryRewriter 实例

        @param llm_provider: Mock LLM Provider
        @type  llm_provider: MagicMock
        @param prompts_dir: 临时 prompts 目录
        @type  prompts_dir: str

        @return: QueryRewriter 实例
        @rtype: QueryRewriter
        """
        return QueryRewriter(llm_provider=llm_provider, prompts_dir=prompts_dir)

    # ---- 测试用例 ----

    def test_normal_json_parsing(self, rewriter, llm_provider):
        """正常 JSON 解析: mock LLM 返回合法 JSON,
        验证 rewrite() 返回正确的 dict
        """
        llm_provider.chat.return_value = json.dumps({
            "keywords": "Kubernetes 自动伸缩",
            "refined_query": "如何在Kubernetes中配置自动伸缩",
        })
        result = rewriter.rewrite("怎么在k8s里配自动伸缩啊")
        assert result == {
            "keywords": "Kubernetes 自动伸缩",
            "refined_query": "如何在Kubernetes中配置自动伸缩",
        }

    def test_markdown_code_block(self, rewriter, llm_provider):
        """Markdown 代码块包裹: mock LLM 返回 ```json...```,
        验证剥离代码块后正确解析
        """
        llm_provider.chat.return_value = (
            '```json\n'
            '{"keywords": "K8s", "refined_query": "K8s自动伸缩配置"}\n'
            '```'
        )
        result = rewriter.rewrite("k8s自动伸缩")
        assert result == {
            "keywords": "K8s",
            "refined_query": "K8s自动伸缩配置",
        }

    def test_invalid_json_fallback(self, rewriter, llm_provider):
        """非法 JSON 降级: mock LLM 返回纯文本,
        验证降级返回原始查询
        """
        llm_provider.chat.return_value = "这是一段纯文本，不是 JSON"
        result = rewriter.rewrite("如何配置Kubernetes")
        assert result == {
            "keywords": "如何配置Kubernetes",
            "refined_query": "如何配置Kubernetes",
        }

    def test_llm_exception_fallback(self, rewriter, llm_provider):
        """LLM 异常降级: mock LLM 的 chat() 抛出异常,
        验证降级返回原始查询
        """
        llm_provider.chat.side_effect = RuntimeError("LLM API 超时")
        result = rewriter.rewrite("Python异常处理")
        assert result == {
            "keywords": "Python异常处理",
            "refined_query": "Python异常处理",
        }

    def test_llm_returns_none(self, rewriter, llm_provider):
        """LLM 返回 None: 验证降级返回原始查询"""
        llm_provider.chat.return_value = None
        result = rewriter.rewrite("数据库性能优化")
        assert result == {
            "keywords": "数据库性能优化",
            "refined_query": "数据库性能优化",
        }

    def test_json_missing_refined_query(self, rewriter, llm_provider):
        """JSON 缺少 refined_query 字段: 验证缺失字段回退为原始查询"""
        llm_provider.chat.return_value = json.dumps({"keywords": "测试"})
        result = rewriter.rewrite("测试用例")
        assert result == {
            "keywords": "测试",
            "refined_query": "测试用例",
        }

    def test_json_missing_keywords(self, rewriter, llm_provider):
        """JSON 缺少 keywords 字段: 验证缺失字段回退为原始查询"""
        llm_provider.chat.return_value = json.dumps({"refined_query": "精炼查询"})
        result = rewriter.rewrite("原始关键词查询")
        assert result == {
            "keywords": "原始关键词查询",
            "refined_query": "精炼查询",
        }

    def test_json_missing_both_fields(self, rewriter, llm_provider):
        """JSON 两个字段都缺失: 验证都回退为原始查询"""
        llm_provider.chat.return_value = json.dumps({"unrelated": "data"})
        result = rewriter.rewrite("无关返回")
        assert result == {
            "keywords": "无关返回",
            "refined_query": "无关返回",
        }

    def test_empty_query(self, rewriter, llm_provider):
        """空查询: 传入空字符串, 验证不会崩溃"""
        llm_provider.chat.return_value = json.dumps({
            "keywords": "",
            "refined_query": "",
        })
        result = rewriter.rewrite("")
        assert result == {"keywords": "", "refined_query": ""}
