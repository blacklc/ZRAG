from abc import ABC, abstractmethod

from zrag.models.document import RawDocument, Chunk


class ChunkingStrategy(ABC):
    """文档分块策略抽象基类

    定义将原始文档切分为多个 Chunk 的统一接口。
    所有具体的分块策略（如 ParagraphChunker、RecursiveCharacterChunker 等）
    必须继承此类并实现 chunk() 方法。

    chunk() 接收一个 RawDocument 作为输入,
    返回该文档对应的 Chunk 列表。
    """

    @abstractmethod
    def chunk(self, document: RawDocument) -> list[Chunk]:
        """将原始文档切分为多个 Chunk

        @param document: 待分块的原始文档
        @type  document: RawDocument

        @return: 分块后的 Chunk 列表
        @type:   list[Chunk]

        @raises: 分块过程中发生错误
        @type:   ValueError
        """
        ...
