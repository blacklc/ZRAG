"""本地 Embedding 模型实现"""
import os

os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from sentence_transformers import SentenceTransformer

from zrag.embed.base import EmbeddingModel


class BgeSmallEmbedder(EmbeddingModel):
    """基于 BAAI/bge-small-zh-v1.5 的本地 Embedding 实现

    使用 sentence-transformers 库加载 BGE 小型中文嵌入模型。
    输出 512 维向量, 已启用 normalize_embeddings=True 以便后续使用 Cosine 距离。

    @param model_name: HuggingFace 模型名称, defaults to "BAAI/bge-small-zh-v1.5"
    @type  model_name: str, optional
    @param cache_dir: 模型缓存目录, 用于指定预下载模型的存放位置, defaults to None
    @type  cache_dir: str, optional
    """

    def __init__(
        self, model_name: str = "BAAI/bge-small-zh-v1.5", cache_dir: str | None = None
    ):
        self._model = SentenceTransformer(model_name, cache_folder=cache_dir)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """将批量文本转换为 512 维向量

        @param texts: 待向量化的文本列表
        @type  texts: list[str]

        @return: 每个文本对应的 512 维向量列表
        @type:   list[list[float]]

        @raises: 模型加载失败或显存不足
        @type:   Exception
        """
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, query: str) -> list[float]:
        """将单条查询转换为 512 维向量

        @param query: 用户输入查询
        @type  query: str

        @return: 查询的 512 维向量
        @type:   list[float]

        @raises: 同 embed()
        @type:   Exception
        """
        return self.embed([query])[0]

    @property
    def dimension(self) -> int:
        """嵌入向量维度

        @return: 512
        @type:   int
        """
        return 512
