"""zrag.ingest.chunking.paragraph — 按段落分块策略"""

from zrag.ingest.chunking.base import ChunkingStrategy
from zrag.models.document import RawDocument, Chunk


class ParagraphChunker(ChunkingStrategy):
    """按段落分块策略

    将文档按 \\n\\n 分割为段落, 每个段落作为一个独立的 Chunk。
    若单个段落超过 max_size 字符, 则截断。
    若段落小于 min_size, 则合并到前一个 Chunk（如果存在）。

    @param max_size: 单个 Chunk 最大字符数, defaults to 512
    @type  max_size: int, optional
    @param min_size: 单个 Chunk 最小字符数, defaults to 50
    @type  min_size: int, optional
    """

    def __init__(self, max_size: int = 512, min_size: int = 50):
        self.max_size = max_size
        self.min_size = min_size

    def _resolve_title(self, document) -> str:
        """解析文档标题，保证非空

        优先级: metadata.title -> fallback(source_type_source_id)
        """
        title = (document.metadata.get("title") or "") if document.metadata else ""
        if not title:
            title = f"{document.source_type}_{document.source_id}"
        return title

    def chunk(self, document: RawDocument) -> list[Chunk]:
        """将原始文档按段落切分为多个 Chunk

        @param document: 待分块的原始文档
        @type  document: RawDocument

        @return: 分块后的 Chunk 列表
        @type:   list[Chunk]
        """
        paragraphs = [p.strip() for p in document.content.split("\n\n") if p.strip()]
        chunks = []
        idx = 0
        for para in paragraphs:
            if len(para) < self.min_size:
                # 小段落合并到前一个 chunk（如果存在）
                if chunks:
                    chunks[-1] = Chunk(
                        chunk_id=chunks[-1].chunk_id,
                        source_id=chunks[-1].source_id,
                        source_type=chunks[-1].source_type,
                        doc_title=chunks[-1].doc_title,
                        content=chunks[-1].content + "\n\n" + para,
                        chunk_index=chunks[-1].chunk_index,
                    )
                else:
                    chunks.append(Chunk(
                        chunk_id=f"{document.source_id}_chunk_{idx}",
                        source_id=document.source_id,
                        source_type=document.source_type,
                        doc_title=self._resolve_title(document),
                        content=para,
                        chunk_index=idx,
                    ))
                    idx += 1
                continue
            chunks.append(Chunk(
                chunk_id=f"{document.source_id}_chunk_{idx}",
                source_id=document.source_id,
                source_type=document.source_type,
                doc_title=self._resolve_title(document),
                content=para[:self.max_size],
                chunk_index=idx,
            ))
            idx += 1
        return chunks
