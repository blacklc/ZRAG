from abc import ABC, abstractmethod
from typing import Iterator

from zrag.models.document import RawDocument


class DocumentSource(ABC):
    """文档数据源抽象基类

    定义从不同来源获取原始文档的统一接口。
    所有具体的数据源实现（如 MacNotesSource）必须继承此类并实现全部抽象方法。

    fetch_batch() 用于分批次获取文档, 支持批量处理以控制内存占用。
    source_type 属性标识数据源类型, 用于配置路由和统计。
    """

    @abstractmethod
    def fetch_batch(self, batch_size: int = 10) -> Iterator[list[RawDocument]]:
        """分批获取原始文档

        每次调用生成一个包含最多 batch_size 条文档的列表。
        调用者可通过迭代此生成器逐个批次处理所有文档。

        @param batch_size: 每批次最大文档数量, defaults to 10
        @type  batch_size: int, optional

        @return: 生成器, 每次 yield 一个 RawDocument 列表
        @type:   Iterator[list[RawDocument]]
        """
        yield []

    @property
    @abstractmethod
    def source_type(self) -> str:
        """获取数据源类型标识

        @return: 数据源类型字符串, 如 "mac_notes" | "local_file"
        @type:   str
        """
        ...
