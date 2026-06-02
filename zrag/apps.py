import os

from django.apps import AppConfig


class ZragConfig(AppConfig):
    """ZRAG Django 应用配置类

    负责应用级别的初始化配置。
    在 ready() 方法中自动执行业务表的建表初始化以及 ChromaDB 向量集合的初始化,
    确保 Django 启动时数据库表结构和向量集合已就绪。
    """

    name = 'zrag'
    verbose_name = 'ZRAG'

    def ready(self):
        from zrag.store.sqlite_store import SQLiteStore
        # 确保数据库存储目录存在
        os.makedirs('data', exist_ok=True)
        store = SQLiteStore()
        store.init_db()

        # ChromaDB 初始化（自动创建 data/ 目录下的 chroma_db/）
        from zrag.store.vector_store import ChromaStore
        ChromaStore(persist_dir='data/chroma_db').init_collection()
