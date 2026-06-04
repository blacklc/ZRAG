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

        # ChromaDB 初始化（自动创建 data/ 目录下的 chroma_db/）
        from zrag.store.vector_store import ChromaStore
        ChromaStore(persist_dir=chroma_path).init_collection()
