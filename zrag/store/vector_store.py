"""ChromaDB 向量存储操作封装

提供对 ChromaDB 向量数据库的 CRUD 操作封装。
内部使用 PersistentClient 管理持久化存储，Collection 名固定为 'zrag_docs'。
支持 Cosine 距离的向量相似度搜索、按 source_id 批量删除等功能。
"""

import chromadb
from chromadb.config import Settings as ChromaSettings


class ChromaStore:
    """ChromaDB 向量存储操作封装类

    封装 ChromaDB 的 PersistentClient 和 Collection 提供简化接口。
    负责 ZRAG 系统中文档向量的增删查操作。

    @param persist_dir: ChromaDB 持久化数据存储目录路径
    @type  persist_dir: str
    """

    def __init__(self, persist_dir: str):
        """构造方法

        @param persist_dir: ChromaDB 持久化数据的存储目录, 若不存在则自动创建
        @type  persist_dir: str
        """
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="zrag_docs",
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
        """向集合中添加向量记录

        批量添加向量数据及其元数据到 ChromaDB 集合中。
        若 ids 中存在已存在的 ID, 默认行为是覆盖更新。

        @param ids: 向量记录的唯一标识列表
        @type  ids: list[str]
        @param embeddings: 向量数据列表, 每个元素为一个 float 列表
        @type  embeddings: list[list[float]]
        @param metadatas: 元数据字典列表, 每个元素包含 source_id / source_type 等字段
        @type  metadatas: list[dict]

        @raises: 当 ids / embeddings / metadatas 列表长度不一致时触发
        @type:   ValueError
        """
        if not ids:
            return
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def similarity_search(self, query_vector: list[float], k: int = 10) -> list[dict]:
        """执行余弦相似度向量检索

        基于 Cosine 距离计算 query_vector 与集合中所有向量的相似度,
        返回最相似的 k 条记录, 已按相似度降序排列。

        @param query_vector: 查询向量
        @type  query_vector: list[float]
        @param k: 返回结果的最大数量, defaults to 10
        @type  k: int, optional

        @return: 检索结果列表, 每条包含 id / metadata / distance 字段
        @type:   list[dict]
        """
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=k,
        )
        output = []
        ids = results['ids'][0]
        distances = results['distances'][0]
        metadatas = results['metadatas'][0]
        for i in range(len(ids)):
            output.append({
                'id': ids[i],
                'metadata': metadatas[i] or {},
                'distance': distances[i],
            })
        return output

    def delete_by_source(self, source_id: str) -> None:
        """删除指定源文档的所有向量记录

        根据 metadatas 中的 source_id 字段过滤并删除对应的向量记录。

        @param source_id: 源文档的唯一标识
        @type  source_id: str
        """
        self._collection.delete(where={"source_id": source_id})

    def count(self) -> int:
        """获取集合中的向量总数

        @return: 当前集合中存储的向量数量
        @type:   int
        """
        return self._collection.count()
