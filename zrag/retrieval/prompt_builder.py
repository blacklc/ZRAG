"""RAG Prompt 构建器

基于 Jinja2 模板引擎将检索结果拼接到 system prompt 中,
生成 OpenAI 格式的消息列表，供下游 LLM Provider 调用。

模板文件位于 zrag/prompts/ 目录。
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
_env = Environment(loader=FileSystemLoader(str(_prompts_dir)))


def build_rag_prompt(query: str, results: list) -> list[dict]:
    """构建 RAG 问答 Prompt

    加载 chat_system.j2 模板, 将检索结果传入 reference_materials 变量,
    每个结果需包含 doc_title 和 content 字段。
    返回 OpenAI 格式的消息列表。

    @param query: 用户提问
    @type  query: str
    @param results: 检索结果列表, 元素需包含 doc_title 和 content 属性
    @type  results: list

    @return: [{"role": "system", "content": "..."}, {"role": "user", "content": query}]
    @rtype:   list[dict]
    """
    materials = [
        {"doc_title": r.doc_title, "content": r.content}
        for r in results
    ]
    template = _env.get_template("chat_system.j2")
    system_msg = template.render(reference_materials=materials)
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": query},
    ]
