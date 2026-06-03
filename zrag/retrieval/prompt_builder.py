"""RAG Prompt 构建器

将检索结果拼接到 system prompt 中, 生成 OpenAI 格式的消息列表,
供下游 LLM Provider 调用。
"""

SYSTEM_PROMPT = """你是一个个人知识库助手。请基于以下参考材料回答用户问题。
如果参考材料中没有相关信息，请如实告知。

参考材料:
{context}"""


def build_rag_prompt(query: str, results: list) -> list[dict]:
    """构建 RAG 问答 Prompt

    将检索结果拼接到 system prompt 的 context 中,
    返回 OpenAI 格式的消息列表。

    每个检索结果按如下格式拼接入 context:
      [来源: {doc_title}]
      {content}

    多条结果之间用 "---" 分隔。

    @param query: 用户提问
    @type  query: str
    @param results: 检索结果列表, 元素需包含 doc_title 和 content 属性
    @type  results: list

    @return: [{"role": "system", "content": "..."}, {"role": "user", "content": query}]
    @type:   list[dict]
    """
    context_lines = [
        f"[来源: {r.doc_title}]\n{r.content}" for r in results
    ]
    context = "\n\n---\n\n".join(context_lines)
    system_msg = SYSTEM_PROMPT.format(context=context)
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": query},
    ]
