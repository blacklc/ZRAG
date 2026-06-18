"""切片 106a4: ConversationSummarizer 单元测试

测试 ConversationSummarizer 的 summarize 方法，包括:
- 首轮对话摘要生成
- 增量摘要压缩
- 前缀清理
- 长度截断
- 助手回复截断
- 非 JSON 格式输出
"""

import os
import tempfile

from unittest.mock import MagicMock

import pytest

from zrag.retrieval.conversation_summarizer import ConversationSummarizer


class TestConversationSummarizer:
    """ConversationSummarizer 单元测试"""

    @pytest.fixture
    def templates_dir(self):
        """创建临时 templates 目录，内含最小化 compress.j2 模板

        @yield: 临时目录路径
        @rtype: str
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = os.path.join(tmpdir, 'compress.j2')
            with open(template_path, 'w') as f:
                f.write("""请生成不超过{{ max_chars }}字的对话摘要。
只输出摘要文本本身。""")
            yield tmpdir

    @pytest.fixture
    def llm_provider(self):
        """创建 Mock LLM Provider (提供 chat() 方法)

        @return: MagicMock 实例
        @rtype: MagicMock
        """
        return MagicMock()

    @pytest.fixture
    def summarizer(self, llm_provider, templates_dir):
        """构造 ConversationSummarizer 实例

        @param llm_provider: Mock LLM Provider
        @type  llm_provider: MagicMock
        @param templates_dir: 临时 templates 目录
        @type  templates_dir: str

        @return: ConversationSummarizer 实例
        @rtype: ConversationSummarizer
        """
        return ConversationSummarizer(
            llm_provider=llm_provider,
            template_dir=templates_dir,
            max_chars=200,
        )

    # ---- 测试用例 ----

    def test_summarize_first_turn(self, summarizer, llm_provider):
        """首轮对话摘要: mock LLM 返回纯文本摘要,
        验证 summarize() 返回非空摘要
        """
        llm_provider.chat.return_value = "用户询问了关于Kubernetes自动伸缩配置的问题。"
        result = summarizer.summarize("", "怎么在k8s里配自动伸缩啊", "可以在Kubernetes中配置HPA来实现自动伸缩。")
        assert result == "用户询问了关于Kubernetes自动伸缩配置的问题。"

    def test_summarize_incremental(self, summarizer, llm_provider):
        """增量摘要: mock LLM 返回融合后的摘要,
        验证传入非空 old_summary 时能正确生成增量摘要
        """
        llm_provider.chat.return_value = "用户询问了Kubernetes自动伸缩配置，并进一步了解了HPA的具体参数设置方法。"
        result = summarizer.summarize(
            "用户询问了关于Kubernetes自动伸缩配置的问题。",
            "HPA的具体参数怎么设置",
            "可以通过kubectl edit hpa命令修改minReplicas和maxReplicas参数。",
        )
        assert result == "用户询问了Kubernetes自动伸缩配置，并进一步了解了HPA的具体参数设置方法。"

    def test_clean_summary_removes_prefixes(self, summarizer):
        """前缀清理: 验证 _clean_summary 能正确移除所有废话前缀"""
        # 测试 "好的，" 前缀
        assert summarizer._clean_summary("好的，用户询问了Kubernetes配置问题。") == "用户询问了Kubernetes配置问题。"

        # 测试 "更新后的摘要：" 前缀（全角冒号）
        assert summarizer._clean_summary("更新后的摘要：用户询问了Kubernetes配置问题。") == "用户询问了Kubernetes配置问题。"

        # 测试 "摘要：" 前缀（全角冒号）
        assert summarizer._clean_summary("摘要：用户询问了Kubernetes配置问题。") == "用户询问了Kubernetes配置问题。"

        # 测试 "总结：" 前缀（全角冒号）
        assert summarizer._clean_summary("总结：用户询问了Kubernetes配置问题。") == "用户询问了Kubernetes配置问题。"

    def test_clean_summary_truncates(self, summarizer):
        """长度截断: 输入文本超过 max_chars 时验证截断到 max_chars"""
        long_text = "用户询问了关于Kubernetes自动伸缩配置的问题，包括HPA的基本原理和具体参数设置方法。"
        # max_chars=200, 上面的文本只有60多字，不会触发截断
        # 构造一个超长文本
        ultra_long = "测试" * 200  # 400字
        result = summarizer._clean_summary(ultra_long)
        assert len(result) == 200

    def test_reply_truncation(self, summarizer, llm_provider):
        """回复截断: 传入超长 assistant_reply（超过500字符），
        验证 LLM 收到的 user message 中包含截断后的回复（500字符）
        """
        llm_provider.chat.return_value = "测试摘要"
        long_reply = "A" * 1000
        summarizer.summarize("", "测试查询", long_reply)

        llm_provider.chat.assert_called_once()
        args, _ = llm_provider.chat.call_args
        messages = args[0]
        user_content = messages[1]["content"]
        # 验证助手回答部分被截断到 500 字符
        assert "A" * 500 in user_content
        assert "A" * 501 not in user_content

    def test_summarize_returns_text_not_json(self, summarizer, llm_provider):
        """非 JSON 格式输出: mock LLM 返回纯文本摘要，
        验证返回结果是普通文本而非 JSON 结构
        """
        llm_provider.chat.return_value = "用户询问了关于Python异常处理的最佳实践。"
        result = summarizer.summarize("", "Python异常处理", "可以使用try-except块来捕获异常。")

        # 验证返回值是普通字符串，非 JSON 格式
        assert isinstance(result, str)
        assert not result.startswith("{")
        assert not result.startswith("[")
        assert "用户询问了关于Python异常处理的最佳实践。" == result
