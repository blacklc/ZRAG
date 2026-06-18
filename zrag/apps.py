import os
from pathlib import Path

from django.apps import AppConfig


class ZragConfig(AppConfig):
    """ZRAG Django 应用配置类

    负责应用级别的初始化配置。
    在 ready() 方法中自动执行业务表的建表初始化以及 ChromaDB 向量集合的初始化,
    确保 Django 启动时数据库表结构和向量集合已就绪。
    存储路径从 Django settings.ZRAG_STORAGE 配置中读取。
    """

    name = 'zrag'
    verbose_name = 'ZRAG'

    def ready(self):
        from django.conf import settings
        storage_cfg = getattr(settings, "ZRAG_STORAGE", {})
        db_path = storage_cfg.get("sqlite_path", "data/zrag.db")
        chroma_path = storage_cfg.get("chroma_path", "data/chroma_db")

        # 确保数据库存储目录存在
        base_dir = Path(db_path).parent
        os.makedirs(str(base_dir), exist_ok=True)

        from zrag.store.sqlite_store import SQLiteStore
        store = SQLiteStore(db_path)
        store.init_db()

        # ChromaDB 初始化（单例模式，避免 SQLite 锁冲突）
        from zrag.store.vector_store import get_chroma_store
        get_chroma_store(persist_dir=chroma_path).init_collection()

        # 预加载 BGE Embedding 模型（单例模式，避免重复加载）
        # 注意: 若 HuggingFace 网络不可达, 模型将延迟到首次使用时加载
        try:
            from zrag.embed.local import get_embedder
            get_embedder()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Embedding 模型预加载失败, 将在首次使用时延迟加载", extra={"error": str(e)})
