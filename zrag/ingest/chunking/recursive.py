"""zrag.ingest.chunking.recursive — 递归字符分割分块策略"""

from zrag.ingest.chunking.base import ChunkingStrategy
from zrag.models.document import RawDocument, Chunk


class RecursiveCharacterChunker(ChunkingStrategy):
    """递归字符分割分块策略（兜底策略）

    按优先级别尝试分割点: \\n\\n → \\n → 句子边界 → 逗号 → 空格。
    确保每块不超过 max_size, 并支持相邻 Chunk 之间的字符重叠。

    @param max_size: 单个 Chunk 最大字符数, defaults to 512
    @type  max_size: int, optional
    @param overlap: 相邻 Chunk 之间的重叠字符数, defaults to 64
    @type  overlap: int, optional
    """

    SEPARATORS = ["\n\n", "\n", "。", "！", "？", "，", "、", " "]

    def __init__(self, max_size: int = 512, overlap: int = 64):
        self.max_size = max_size
        self.overlap = overlap

    def chunk(self, document: RawDocument) -> list[Chunk]:
        """将原始文档通过递归字符分割切分为多个 Chunk

        @param document: 待分块的原始文档
        @type  document: RawDocument

        @return: 分块后的 Chunk 列表
        @type:   list[Chunk]
        """
        segments = self._split_text(document.content)

        # 添加重叠字符（仅在顶层，避免递归中重复应用）
        if self.overlap > 0 and len(segments) > 1:
            overlapped = [segments[0]]
            for i in range(1, len(segments)):
                prev = segments[i - 1]
                overlap_len = min(self.overlap, len(prev))
                overlap_text = prev[-overlap_len:]
                overlapped.append(overlap_text + segments[i])
            segments = overlapped

        chunks = []
        for i, seg in enumerate(segments):
            chunks.append(Chunk(
                chunk_id=f"{document.source_id}_chunk_{i}",
                source_id=document.source_id,
                source_type=document.source_type,
                doc_title=document.metadata.get("title", "") if document.metadata else "",
                content=seg,
                chunk_index=i,
            ))
        return chunks

    def _split_text(self, text: str, separators: list[str] = None) -> list[str]:
        """递归分割文本, 保证每块 <= max_size

        按优先级依次尝试各分隔符进行分割。
        若当前分隔符不在文本中, 则尝试下一级分隔符。
        若分隔符分割后的某个片段仍超过 max_size, 则递归调用下一级分隔符继续分割。
        所有分隔符都不适用时, 直接按 max_size 截断。

        @param text: 待分割的文本
        @type  text: str
        @param separators: 待尝试的分隔符列表, defaults to None
                            为 None 时使用实例的 SEPARATORS 类属性
        @type  separators: list[str], optional

        @return: 分割后的文本片段列表
        @type:   list[str]
        """
        if separators is None:
            separators = list(self.SEPARATORS)

        if len(text) <= self.max_size:
            return [text]

        # 尝试当前第一个分隔符
        sep = separators[0] if separators else ""

        if not sep:
            # 没有更多分隔符, 直接截断
            return [text[i:i + self.max_size] for i in range(0, len(text), self.max_size)]

        if sep not in text:
            # 当前分隔符不在文本中, 尝试下一级
            return self._split_text(text, separators[1:])

        parts = text.split(sep)
        results = []
        next_seps = separators[1:] if len(separators) > 1 else []

        for part in parts:
            if not part:
                continue
            if len(part) > self.max_size:
                # 片段仍然超长, 递归切割
                if next_seps:
                    sub_results = self._split_text(part, next_seps)
                    results.extend(sub_results)
                else:
                    # 没有更多分隔符, 直接截断
                    for i in range(0, len(part), self.max_size):
                        results.append(part[i:i + self.max_size])
            else:
                # 尝试合并到前一个结果以避免过多碎片
                if results and len(results[-1]) + len(sep) + len(part) <= self.max_size:
                    results[-1] = results[-1] + sep + part
                else:
                    results.append(part)

        return results
