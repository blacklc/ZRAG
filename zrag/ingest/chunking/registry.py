"""zrag.ingest.chunking.registry — 分块策略注册表"""

from zrag.ingest.chunking.paragraph import ParagraphChunker
from zrag.ingest.chunking.recursive import RecursiveCharacterChunker
from zrag.ingest.chunking.composite import CompositeChunker
from zrag.ingest.chunking.heading import HeadingChunker

# 默认注册表: source_type → ChunkingStrategy
CHUNKER_REGISTRY = {
    "mac_notes": CompositeChunker(
        HeadingChunker(levels=[1, 2, 3], max_size=1000, min_size=200, overlap=100),
        RecursiveCharacterChunker(max_size=1000, overlap=100),
        max_size=1000,
    ),
    "default": RecursiveCharacterChunker(),
}


def get_chunker(source_type: str) -> object:
    """根据 source_type 获取对应的分块策略

    @param source_type: 文档来源类型
    @type  source_type: str

    @return: 对应的分块策略实例
    @type:   ChunkingStrategy
    """
    return CHUNKER_REGISTRY.get(source_type, CHUNKER_REGISTRY["default"])
