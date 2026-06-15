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
        self, model_name: str | None = None, cache_dir: str | None = None
    ):
        """构造 BgeSmallEmbedder

        若 model_name 或 cache_dir 未显式传入，则从 Django settings.ZRAG_EMBEDDING 配置中读取。
        配置中也缺失时抛出 ValueError。

        @param model_name: HuggingFace 模型名称, defaults to None
                            未传入则从配置读取
        @type  model_name: str, optional
        @param cache_dir: 模型缓存目录, defaults to None
                          未传入则从配置读取
        @type  cache_dir: str, optional

        @raises ValueError: model_name 或 cache_dir 在参数和配置中均未提供时抛出
        """
        if model_name is not None and cache_dir is not None:
            m_name, c_dir = model_name, cache_dir
        else:
            from django.conf import settings
            emb_cfg = getattr(settings, "ZRAG_EMBEDDING", {})
            m_name = model_name or emb_cfg.get("model_name")
            c_dir = cache_dir or emb_cfg.get("cache_dir")
            if not m_name or not c_dir:
                raise ValueError(
                    "配置缺失: embedding.model_name 或 embedding.cache_dir, "
                    "请检查 config/embedding.yaml 或设置 MODELS_DIR 环境变量"
                )
        self._model = SentenceTransformer(
            m_name, cache_folder=c_dir, local_files_only=True,
        )
        self._query_instruction = "为这个句子生成表示以用于检索相关文章："

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
        """将单条查询转换为 512 维向量, 自动添加 BGE 指令前缀

        @param query: 用户输入查询
        @type  query: str

        @return: 查询的 512 维向量
        @type:   list[float]

        @raises: 同 embed()
        @type:   Exception
        """
        return self.embed([self._query_instruction + query])[0]

    @property
    def dimension(self) -> int:
        """嵌入向量维度

        @return: 512
        @type:   int
        """
        return 512


# 模块级单例, 由 get_embedder() 管理
_embedder_instance = None


def get_embedder(
    model_name: str | None = None, cache_dir: str | None = None,
) -> BgeSmallEmbedder:
    """获取 BgeSmallEmbedder 模块级单例

    避免在 uWSGI worker 中重复创建 SentenceTransformer 实例,
    防止模型重复加载导致请求挂死。

    @param model_name: 模型名称, 仅首次调用时生效, defaults to None
    @type  model_name: str, optional
    @param cache_dir: 模型缓存目录, 仅首次调用时生效, defaults to None
    @type  cache_dir: str, optional

    @return: BgeSmallEmbedder 全局唯一实例
    @rtype:  BgeSmallEmbedder
    """
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = BgeSmallEmbedder(
            model_name=model_name, cache_dir=cache_dir,
        )
    return _embedder_instance
