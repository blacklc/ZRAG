"""zrag.ingest.chunking.composite — 组合分块策略"""

from zrag.ingest.chunking.base import ChunkingStrategy
from zrag.ingest.chunking.paragraph import ParagraphChunker
from zrag.ingest.chunking.recursive import RecursiveCharacterChunker
from zrag.models.document import RawDocument, Chunk


class CompositeChunker(ChunkingStrategy):
    """组合分块策略

    先用主策略（ParagraphChunker）分块, 再对超过 max_size 的块
    交给兜底策略（RecursiveCharacterChunker）递归切割。
    适用于需要对多数正常段落保持完整、仅对超长段落进行进一步切割的场景。

    @param primary: 主分块策略, defaults to None
    @type  primary: ChunkingStrategy, optional
    @param fallback: 兜底分块策略, defaults to None
    @type  fallback: ChunkingStrategy, optional
    @param max_size: Chunk 最大字符数, defaults to 512
    @type  max_size: int, optional
    """

    def __init__(self, primary=None, fallback=None, max_size=512):
        self.primary = primary or ParagraphChunker(max_size=max_size)
        # 兜底策略不设置 overlap, 因为主策略已保证段落结构
        self.fallback = fallback or RecursiveCharacterChunker(max_size=max_size, overlap=0)
        self.max_size = max_size

    def chunk(self, document: RawDocument) -> list[Chunk]:
        """使用组合策略将文档切分为多个 Chunk

        先用 ParagraphChunker 进行段落分块,
        然后对超过 max_size 的块使用 RecursiveCharacterChunker 进一步切割,
        最后对所有 Chunk 重新编号。

        @param document: 待分块的原始文档
        @type  document: RawDocument

        @return: 分块后的 Chunk 列表
        @type:   list[Chunk]
        """
        primary_chunks = self.primary.chunk(document)
        result = []
        idx = 0

        for c in primary_chunks:
            if len(c.content) > self.max_size:
                # 超长块, 交给兜底策略递归切割
                sub_raw = RawDocument(
                    source_id=c.source_id,
                    source_type=c.source_type,
                    content=c.content,
                    content_hash="",
                    metadata={"title": c.doc_title},
                )
                sub_chunks = self.fallback.chunk(sub_raw)
                for sub in sub_chunks:
                    result.append(Chunk(
                        chunk_id=f"{c.source_id}_chunk_{idx}",
                        source_id=c.source_id,
                        source_type=c.source_type,
                        doc_title=c.doc_title,
                        content=sub.content,
                        chunk_index=idx,
                    ))
                    idx += 1
            else:
                # 正常块, 直接通过
                result.append(Chunk(
                    chunk_id=f"{c.source_id}_chunk_{idx}",
                    source_id=c.source_id,
                    source_type=c.source_type,
                    doc_title=c.doc_title,
                    content=c.content,
                    chunk_index=idx,
                ))
                idx += 1

        return result
