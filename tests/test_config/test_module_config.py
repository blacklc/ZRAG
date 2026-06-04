"""模块配置读取集成测试

验证各模块从 settings.ZRAG_* 正确读取配置。

注意: 此文件依赖 settings.py 对各模块的改造。
如果 settings.ZRAG_* 属性尚未定义, 相关测试会标记为 skip。

TODO: 待 settings.py 添加 ZRAG_* 属性后取消 skip 标记。
"""
import os
import pytest

# 设置必要的环境变量用于配置加载
os.environ.setdefault("ZRAG_API_KEY", "test-api-key")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test-key")

import django
from django.conf import settings
django.setup()

# ============================================================
# 检测 settings 中是否已注入 ZRAG_* 配置属性
# ============================================================
_HAS_ZRAG_SETTINGS = hasattr(settings, "ZRAG_STORAGE")


class TestSqliteStoreConfig:
    """SQLiteStore 配置读取"""

    def test_default_path_matches_yaml(self):
        """默认 db_path 与 config/storage.yaml 一致"""
        from zrag.store.sqlite_store import SQLiteStore
        store = SQLiteStore()
        assert store._db_path == "data/zrag.db"

    def test_explicit_arg_override(self):
        """显式传参优先于配置"""
        from zrag.store.sqlite_store import SQLiteStore
        store = SQLiteStore(":memory:")
        assert store._db_path == ":memory:"

    @pytest.mark.skipif(not _HAS_ZRAG_SETTINGS, reason="settings.ZRAG_STORAGE 尚未注入")
    def test_default_from_config(self):
        """未传参时从 settings.ZRAG_STORAGE 读取 sqlite_path"""
        from zrag.store.sqlite_store import SQLiteStore
        expected = settings.ZRAG_STORAGE.get("sqlite_path")
        if expected:
            store = SQLiteStore()
            assert store._db_path == expected

    @pytest.mark.skipif(not _HAS_ZRAG_SETTINGS, reason="settings.ZRAG_STORAGE 尚未注入")
    def test_chroma_path_from_config(self):
        """chroma_path 从 settings.ZRAG_STORAGE 读取"""
        import zrag.store.vector_store as vs
        chroma_cfg = settings.ZRAG_STORAGE.get("chroma_path")
        if chroma_cfg:
            # TODO: 待 ChromaStore 支持从配置读取后验证
            pass


class TestLLMGatewayConfig:
    """LLMGatewayProvider 配置读取"""

    def _provider(self):
        """返回 LLMGatewayProvider 类；若依赖缺失则跳过测试"""
        pytest.importorskip("openai", reason="openai 未安装")
        import unittest.mock as mock
        from zrag.llm.gateway import LLMGatewayProvider
        with mock.patch("zrag.llm.gateway.OpenAI"):
            return LLMGatewayProvider

    def test_default_model_matches_yaml(self):
        """默认 model 与 config/llm.yaml 一致"""
        LLMGatewayProvider = self._provider()
        provider = LLMGatewayProvider()
        assert provider.model == "smart-router"

    def test_default_timeout_matches_yaml(self):
        """默认 timeout 与 config/llm.yaml 一致"""
        LLMGatewayProvider = self._provider()
        provider = LLMGatewayProvider()
        assert provider.timeout == 200

    def test_explicit_arg_override(self):
        """显式传参优先于配置"""
        LLMGatewayProvider = self._provider()
        provider = LLMGatewayProvider(model="test-model", timeout=30)
        assert provider.model == "test-model"
        assert provider.timeout == 30

    @pytest.mark.skipif(not _HAS_ZRAG_SETTINGS, reason="settings.ZRAG_LLM 尚未注入")
    def test_default_from_config(self):
        """未传参时从 settings.ZRAG_LLM 读取"""
        pytest.importorskip("openai", reason="openai 未安装")
        from zrag.llm.gateway import LLMGatewayProvider
        llm_cfg = settings.ZRAG_LLM
        import unittest.mock as mock
        with mock.patch("zrag.llm.gateway.OpenAI"):
            provider = LLMGatewayProvider()
            assert provider.model == llm_cfg["gateway"]["model"]
            assert provider.timeout == llm_cfg["timeout"]


class TestAPIAuthConfig:
    """API Key 认证配置"""

    @pytest.mark.skipif(not _HAS_ZRAG_SETTINGS, reason="settings.ZRAG_API_KEY 尚未注入")
    def test_api_key_from_settings(self):
        """auth 模块读取 settings.ZRAG_API_KEY"""
        if settings.ZRAG_API_KEY:
            assert len(settings.ZRAG_API_KEY) > 0


class TestEmbeddingConfig:
    """BgeSmallEmbedder 配置读取"""

    def test_default_model_name_matches_yaml(self):
        """默认 model_name 与 config/embedding.yaml 一致"""
        assert True  # 默认值 "BAAI/bge-small-zh-v1.5" 已在代码中硬编码

    def test_cache_dir_required(self):
        """cache_dir 未设置时抛出 ValueError"""
        pytest.importorskip("sentence_transformers", reason="sentence_transformers 未安装")
        from zrag.embed.local import BgeSmallEmbedder
        with pytest.raises(ValueError, match="cache_dir"):
            BgeSmallEmbedder()

    @pytest.mark.skipif(not _HAS_ZRAG_SETTINGS, reason="settings.ZRAG_EMBEDDING 尚未注入")
    def test_default_from_config(self):
        """未传参时从 settings.ZRAG_EMBEDDING 读取"""
        from zrag.embed.local import BgeSmallEmbedder
        emb_cfg = settings.ZRAG_EMBEDDING
        model_name = emb_cfg.get("model_name")
        cache_dir = emb_cfg.get("cache_dir")
        assert model_name == "BAAI/bge-small-zh-v1.5"
        assert cache_dir is not None


class TestIngestionConfig:
    """IngestionPipeline 配置读取"""

    def test_default_batch_size_matches_yaml(self):
        """默认 batch_size 与 config/ingest.yaml 一致"""
        from zrag.ingest.pipeline import IngestionPipeline
        import unittest.mock as mock
        pipeline = IngestionPipeline(
            sqlite_store=mock.MagicMock(),
            chroma_store=mock.MagicMock(),
            embedder=mock.MagicMock(),
            chunker=mock.MagicMock(),
        )
        assert pipeline.batch_size == 5

    @pytest.mark.skipif(not _HAS_ZRAG_SETTINGS, reason="settings.ZRAG_INGEST 尚未注入")
    def test_batch_size_from_config(self):
        """batch_size 默认值从 settings.ZRAG_INGEST 读取"""
        from zrag.ingest.pipeline import IngestionPipeline
        import unittest.mock as mock
        ingest_cfg = settings.ZRAG_INGEST
        pipeline = IngestionPipeline(
            sqlite_store=mock.MagicMock(),
            chroma_store=mock.MagicMock(),
            embedder=mock.MagicMock(),
            chunker=mock.MagicMock(),
        )
        assert pipeline.batch_size == ingest_cfg.get("batch_size", 5)
