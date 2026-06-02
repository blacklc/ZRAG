from dataclasses import dataclass


@dataclass
class SearchResult:
    """检索结果数据类

    表示混合检索（Hybrid Search + RRF）后的单个命中结果。
    由 Retriever 产出, 作为 PromptBuilder 构建 Prompt 的输入数据。

    @param chunk_id: 命中的分块 ID, 以 SQLite chunks 表为准
    @type  chunk_id: str
    @param content: 分块原文, 来源于 SQLite chunks.content
    @type  content: str
    @param doc_title: 所属文档标题
    @type  doc_title: str
    @param source_id: 来源文档标识
    @type  source_id: str
    @param source_type: 来源类型
    @type  source_type: str
    @param score: RRF 融合后的最终相关性分数
    @type  score: float
    """
    chunk_id: str
    content: str
    doc_title: str
    source_id: str
    source_type: str
    score: float
