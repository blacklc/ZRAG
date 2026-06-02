"""Embedding 模型抽象基类"""
from abc import ABC, abstractmethod


class EmbeddingModel(ABC):
    """Embedding 模型抽象基类

    定义文本嵌入模型的统一接口。
    所有具体的嵌入模型实现（如 BgeSmallEmbedder）必须继承此类并实现全部抽象方法。

    embed() 用于批量文本向量化, embed_query() 用于单条用户查询的向量化,
    两者分离是为了支持某些模型对查询和文档使用不同的编码策略。
    """

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """将批量文本转换为向量表示

        @param texts: 待向量化的文本列表
        @type  texts: list[str]

        @return: 向量列表, 每个元素对应一个输入文本的向量表示
        @type:   list[list[float]]
        """
        ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """将单条用户查询转换为向量表示

        某些模型对查询和文档使用不同的编码策略,
        因此与 embed() 分离为独立方法。

        @param query: 用户输入的查询字符串
        @type  query: str

        @return: 查询向量的表示
        @type:   list[float]
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """获取嵌入向量的维度

        @return: 该模型输出的向量维度
        @type:   int
        """
        ...
