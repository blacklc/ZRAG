from dataclasses import dataclass


@dataclass
class RawDocument:
    """原始文档数据类

    表示从 Source 层输出的、尚未经过分块处理的原始文档。
    用于在 IngestionPipeline 中作为 DocumentSource → Chunker 之间的中间数据载体。

    @param source_id: 来源文档的唯一标识
    @type  source_id: str
    @param source_type: 来源类型, 如 "mac_notes" | "local_file"
    @type  source_type: str
    @param content: 清洗后的文档内容, 用于后续分块处理
    @type  content: str
    @param content_hash: SHA256 哈希值, 用于增量同步时的内容变更检测
    @type  content_hash: str
    @param metadata: 额外元数据, 如 chunk_strategy 等配置项, defaults to None
    @type  metadata: dict | None, optional
    """
    source_id: str
    source_type: str
    content: str
    content_hash: str
    metadata: dict | None = None


@dataclass
class Chunk:
    """文档分块数据类

    表示经过 ChunkingStrategy 分块后的单个片段。
    一个 RawDocument 会被切分为多个 Chunk, 每个 Chunk 独立向量化并存入数据库。

    @param chunk_id: 分块的唯一标识, 格式为 "{source_id}_chunk_{index}"
    @type  chunk_id: str
    @param source_id: 所属源文档的标识
    @type  source_id: str
    @param source_type: 来源类型
    @type  source_type: str
    @param doc_title: 文档标题
    @type  doc_title: str
    @param content: 分块后的文本内容
    @type  content: str
    @param chunk_index: 在文档中的分块序号, 从 0 开始
    @type  chunk_index: int
    """
    chunk_id: str
    source_id: str
    source_type: str
    doc_title: str
    content: str
    chunk_index: int
