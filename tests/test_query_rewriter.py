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
                f.write("""你是一个查询优化助手。你的任务是将用户的日常口语化查询改写为更适合检索的结构化格式。

任务说明:
1. 从用户查询中提取核心关键词，用空格分隔，用于全文检索
2. 将用户查询精炼改写为简洁、规范的自然语言查询，用于语义检索
3. 如果提供了对话上下文摘要，请结合摘要识别并消解指代关系。将"它""这个""那个""这些"等指代词替换为上下文中对应的具体实体名称。
4. 关键词提取时注意：对于复合概念术语，只保留最核心的名词，去掉修饰性前缀。例如 "实现原理" 提取为 "原理"。
5. 输出必须是纯 JSON 格式，不要使用 markdown 代码块包裹

输出格式要求:
- 必须输出纯 JSON 对象，不要包含任何 markdown 标记或代码块
- JSON 对象必须包含以下两个字段：
  - "keywords": 空格分隔的关键词字符串，关键词应为核心术语，去除停用词和修饰语
  - "refined_query": 精炼改写后的自然语言查询语句，保持语义不变但更简洁规范
""")
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

    def test_synonym_replacement_in_keywords(self, rewriter, llm_provider):
        """同义词替换: LLM 返回同义词替换后的 keywords, 验证能被正确解析"""
        llm_provider.chat.return_value = json.dumps({
            "keywords": "Kubernetes 默认调度器 工作原理",
            "refined_query": "详细讲解 Kubernetes 默认调度器的实现原理",
        })
        result = rewriter.rewrite("详细讲解Kubernetes默认调度器的实现原理")
        assert result["keywords"] == "Kubernetes 默认调度器 工作原理"
        assert "工作原理" in result["keywords"]
        assert "实现原理" not in result["keywords"]

    def test_synonym_keeps_space_delimited_format(self, rewriter, llm_provider):
        """同义词替换后 keywords 格式验证: 验证仍是空格分隔字符串"""
        llm_provider.chat.return_value = json.dumps({
            "keywords": "容器 编排 工作原理",
            "refined_query": "容器编排的工作原理",
        })
        result = rewriter.rewrite("容器编排是怎么实现的")
        raw_keywords = result["keywords"]
        # 验证是空格分隔的字符串
        tokens = raw_keywords.split()
        assert len(tokens) >= 1
        assert " " in raw_keywords
        # 验证每个 token 都不包含空格
        for token in tokens:
            assert " " not in token

    # ---- 上下文感知改写相关测试 ----

    def test_rewrite_with_summary(self, rewriter, llm_provider):
        """传入对话上下文摘要: 验证摘要被注入到 LLM 消息中"""
        llm_provider.chat.return_value = json.dumps({
            "keywords": "Pod 水平自动伸缩 配置",
            "refined_query": "如何为 Kubernetes Pod 配置水平自动伸缩",
        })
        result = rewriter.rewrite(
            "怎么给它配置自动伸缩",
            summary="用户正在询问 Kubernetes Pod 的水平自动伸缩配置",
        )
        assert result["keywords"] == "Pod 水平自动伸缩 配置"
        assert result["refined_query"] == "如何为 Kubernetes Pod 配置水平自动伸缩"
        # 验证 LLM 收到的消息包含摘要
        llm_provider.chat.assert_called_once()
        args, _ = llm_provider.chat.call_args
        messages = args[0]
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        assert "对话上下文摘要" in messages[1]["content"]
        assert "Pod 的水平自动伸缩配置" in messages[1]["content"]

    def test_rewrite_without_summary(self, rewriter, llm_provider):
        """不传摘要: 验证向后兼容, 行为与旧版本一致"""
        llm_provider.chat.return_value = json.dumps({
            "keywords": "Kubernetes 自动伸缩",
            "refined_query": "如何在 Kubernetes 中配置自动伸缩",
        })
        result = rewriter.rewrite("怎么在k8s里配自动伸缩啊")
        assert result == {
            "keywords": "Kubernetes 自动伸缩",
            "refined_query": "如何在 Kubernetes 中配置自动伸缩",
        }
        # 验证 LLM 收到的 user message 不包含摘要前缀
        llm_provider.chat.assert_called_once()
        args, _ = llm_provider.chat.call_args
        messages = args[0]
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "怎么在k8s里配自动伸缩啊"
        assert "对话上下文摘要" not in messages[1]["content"]

    def test_coreference_resolution(self, rewriter, llm_provider):
        """指代消解: 验证带指代词的查询能被正确改写"""
        llm_provider.chat.return_value = json.dumps({
            "keywords": "Python 文件编码",
            "refined_query": "Python 读取文件时编码错误的原因和解决方法",
        })
        result = rewriter.rewrite(
            "它是什么原因导致的",
            summary="用户在使用 Python 读取文件时遇到了编码错误",
        )
        assert result["keywords"] == "Python 文件编码"
        # 验证 refined_query 中不包含指代词
        assert "它" not in result["refined_query"]
        assert "编码" in result["refined_query"]

    def test_core_term_extraction(self, rewriter, llm_provider):
        """核心词提取: 验证复合概念术语只保留核心名词"""
        llm_provider.chat.return_value = json.dumps({
            "keywords": "Kubernetes 默认调度器 原理",
            "refined_query": "详细讲解 Kubernetes 默认调度器的实现原理",
        })
        result = rewriter.rewrite("详细讲解Kubernetes默认调度器的实现原理")
        assert result["keywords"] == "Kubernetes 默认调度器 原理"
        assert "实现原理" not in result["keywords"]
        assert "原理" in result["keywords"]
