"""切片 106a4: ConversationSummarizer 单元测试

测试 ConversationSummarizer 的 summarize 方法，包括:
- 首轮对话摘要生成
- 增量摘要压缩
- 前缀清理
- 长度截断
- 助手回复截断
- 非 JSON 格式输出
"""

from unittest.mock import MagicMock

import pytest

from zrag.retrieval.conversation_summarizer import ConversationSummarizer


class TestConversationSummarizer:
    """ConversationSummarizer 单元测试"""

    @pytest.fixture
    def llm_provider(self):
        """创建 Mock LLM Provider (提供 chat() 方法)

        @return: MagicMock 实例
        @rtype: MagicMock
        """
        return MagicMock()

    @pytest.fixture
    def summarizer(self, llm_provider):
        """构造 ConversationSummarizer 实例

        @param llm_provider: Mock LLM Provider
        @type  llm_provider: MagicMock

        @return: ConversationSummarizer 实例
        @rtype: ConversationSummarizer
        """
        return ConversationSummarizer(llm_provider=llm_provider)

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
        """回复截断: 传入超长 assistant_reply，
        验证 reply 会根据 context_window 被截断
        """
        llm_provider.chat.return_value = "测试摘要"
        long_reply = "A" * 1000
        # 使用小 context_window 触发截断
        summarizer.summarize("", "测试查询", long_reply, context_window=1044)

        llm_provider.chat.assert_called_once()
        args, _ = llm_provider.chat.call_args
        messages = args[0]
        user_content = messages[1]["content"]
        # 验证完整的 1000 字符回复不在 content 中（已被截断）
        assert "A" * 1000 not in user_content
        assert "测试查询" in user_content

    def test_system_prompt_contains_qa_instructions(self, summarizer):
        """system prompt 包含 Q&A 导向指令, 而非旧的模糊摘要表述

        @param summarizer: ConversationSummarizer 实例
        @type  summarizer: ConversationSummarizer
        """
        messages = summarizer._render_messages(
            old_summary="已有摘要内容",
            user_query="测试问题",
            truncated_reply="测试回答",
        )
        system_prompt = messages[0]["content"]

        # （RED 阶段应失败: 当前模板不含 Q&A 关键词）
        assert any(kw in system_prompt for kw in ["用户提问", "用户询问", "用户关注", "问题"]), \
            "system prompt 应包含用户相关关键词"
        assert any(kw in system_prompt for kw in ["回答", "助手介绍"]), \
            "system prompt 应包含助手回复相关关键词"
        assert any(kw in system_prompt for kw in ["时间线", "追加", "融合", "已有摘要"]), \
            "system prompt 应包含多轮融合相关描述"
        # 确保不只有旧的模糊表述
        assert not ("概括对话主题" in system_prompt and all(
            kw not in system_prompt for kw in ["用户提问", "用户询问", "用户关注"]
        )), "不应只有旧的模糊表述而不含 Q&A 导向内容"

    def test_system_prompt_requires_all_round_questions(self, summarizer):
        """system prompt 应要求保留所有轮次的用户提问，而非仅本轮"""
        messages = summarizer._render_messages(
            old_summary="第1轮：用户询问了K8s自动伸缩。助手介绍了HPA配置。",
            user_query="HPA的具体参数怎么设置",
            truncated_reply="可以通过kubectl edit hpa命令修改minReplicas和maxReplicas参数。",
        )
        system_prompt = messages[0]["content"]

        # 应包含"所有轮次"或"全过程"等覆盖全部轮次的关键词
        assert any(kw in system_prompt for kw in ["全过程", "所有轮次", "每个问题", "不得遗漏", "每轮"]), \
            "system prompt 应要求覆盖全部轮次的用户提问"
        # 应包含优先保留用户提问的指令
        assert any(kw in system_prompt for kw in ["用户提问必须保留", "不得丢弃"]), \
            "system prompt 应要求优先保留用户提问"
        # 不应有仅关注"本轮"的局限表述
        assert "本轮对话中提出了哪些问题" not in system_prompt, \
            "不应只描述本轮对话中的问题"

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
