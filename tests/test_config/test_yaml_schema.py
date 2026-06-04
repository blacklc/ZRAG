"""config/*.yaml 文件结构完整性测试"""
import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class TestYamlLoadable:
    """测试所有 YAML 文件可正常解析"""

    def test_all_files_exist(self):
        """6 个 YAML 文件都存在"""
        expected = ["llm", "embedding", "ingest", "api", "storage", "retrieval"]
        for name in expected:
            f = CONFIG_DIR / f"{name}.yaml"
            assert f.exists(), f"{f} 不存在"

    def test_all_loadable(self):
        """每个 YAML 文件可被 yaml.safe_load 解析"""
        for f in sorted(CONFIG_DIR.glob("*.yaml")):
            data = yaml.safe_load(f.read_text())
            assert data is not None, f"{f.name} 内容为空"


class TestLlmYaml:
    """llm.yaml 字段验证"""

    def test_keys(self):
        data = yaml.safe_load((CONFIG_DIR / "llm.yaml").read_text())["llm"]
        assert data["provider"] == "gateway"
        assert data["gateway"]["model"] == "smart-router"
        assert "timeout" in data
        assert "base_url" in data["gateway"]
        assert "api_key" in data["gateway"]


class TestEmbeddingYaml:
    """embedding.yaml 字段验证"""

    def test_keys(self):
        data = yaml.safe_load((CONFIG_DIR / "embedding.yaml").read_text())["embedding"]
        assert "model_name" in data
        assert "cache_dir" in data
        assert data["device"] == "cpu"


class TestStorageYaml:
    """storage.yaml 字段验证"""

    def test_keys(self):
        data = yaml.safe_load((CONFIG_DIR / "storage.yaml").read_text())["storage"]
        assert data["sqlite_path"] == "data/zrag.db"
        assert data["chroma_path"] == "data/chroma_db"


class TestApiYaml:
    """api.yaml 字段验证"""

    def test_keys(self):
        data = yaml.safe_load((CONFIG_DIR / "api.yaml").read_text())["api"]
        assert "key" in data
        assert data["query_max_length"] == 2000


class TestIngestYaml:
    """ingest.yaml 字段验证"""

    def test_keys(self):
        data = yaml.safe_load((CONFIG_DIR / "ingest.yaml").read_text())["ingest"]
        assert data["batch_size"] == 5


class TestRetrievalYaml:
    """retrieval.yaml 字段验证"""

    def test_keys(self):
        data = yaml.safe_load((CONFIG_DIR / "retrieval.yaml").read_text())["retrieval"]
        assert data["top_k"] == 10
