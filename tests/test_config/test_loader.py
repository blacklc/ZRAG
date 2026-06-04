"""zrag.config.loader 单元测试"""
import os
import pytest
from pathlib import Path


def _write_yaml(tmp_path, filename, content):
    """辅助：往 tmp_path 写入一个 YAML 文件"""
    f = tmp_path / filename
    f.write_text(content)
    return f


class TestLoadEmptyDir:
    """测试 1: config 目录不存在或为空"""

    def test_nonexistent_dir(self):
        """目录不存在时返回空 dict"""
        from zrag.config.loader import load_config
        cfg = load_config("/nonexistent/path")
        assert cfg == {}

    def test_empty_dir(self, tmp_path):
        """空目录返回空 dict"""
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        assert cfg == {}


class TestLoadSingleFile:
    """测试 2: 单个 YAML 文件"""

    def test_single_file(self, tmp_path):
        """单个 YAML 文件正确解析"""
        from zrag.config.loader import load_config
        _write_yaml(tmp_path, "app.yaml", "app:\n  name: zrag")
        cfg = load_config(str(tmp_path))
        assert cfg["app"]["name"] == "zrag"


class TestMergeMultipleFiles:
    """测试 3: 多文件同名 key 合并"""

    def test_merge_top_level(self, tmp_path):
        """不同 top-level key 合并"""
        from zrag.config.loader import load_config
        _write_yaml(tmp_path, "a.yaml", "a: 1")
        _write_yaml(tmp_path, "b.yaml", "b: 2")
        cfg = load_config(str(tmp_path))
        assert cfg["a"] == 1
        assert cfg["b"] == 2

    def test_merge_same_key_dict(self, tmp_path):
        """同 top-level key 的 dict 深度合并"""
        from zrag.config.loader import load_config
        _write_yaml(tmp_path, "base.yaml", "x:\n  a: 1")
        _write_yaml(tmp_path, "ext.yaml", "x:\n  b: 2")
        cfg = load_config(str(tmp_path))
        assert cfg["x"]["a"] == 1
        assert cfg["x"]["b"] == 2

    def test_merge_same_key_scalar(self, tmp_path):
        """同 top-level key 的非 dict 值后覆盖前"""
        from zrag.config.loader import load_config
        _write_yaml(tmp_path, "a.yaml", "x: first")
        _write_yaml(tmp_path, "b.yaml", "x: last")
        cfg = load_config(str(tmp_path))
        assert cfg["x"] == "last"

    def test_sort_order(self, tmp_path):
        """按文件名排序加载"""
        from zrag.config.loader import load_config
        _write_yaml(tmp_path, "zzz.yaml", "z: 1")
        _write_yaml(tmp_path, "aaa.yaml", "a: 2")
        cfg = load_config(str(tmp_path))
        # 两个文件都有各自的 top-level key
        assert "a" in cfg
        assert "z" in cfg


class TestEnvVarSubstitution:
    """测试 4: 环境变量替换"""

    def test_basic_substitution(self, tmp_path):
        """${VAR} 正确替换为环境变量值"""
        from zrag.config.loader import load_config
        os.environ["TEST_DB"] = "mydb"
        _write_yaml(tmp_path, "db.yaml", 'db: "${TEST_DB}"')
        cfg = load_config(str(tmp_path))
        assert cfg["db"] == "mydb"
        del os.environ["TEST_DB"]

    def test_default_syntax(self, tmp_path):
        """${VAR:-default} 未定义时使用默认值"""
        from zrag.config.loader import load_config
        if "TEST_DB2" in os.environ:
            del os.environ["TEST_DB2"]
        _write_yaml(tmp_path, "db.yaml", 'db: "${TEST_DB2:-localhost}"')
        cfg = load_config(str(tmp_path))
        assert cfg["db"] == "localhost"

    def test_default_overridden(self, tmp_path):
        """${VAR:-default} 已定义时使用环境变量值"""
        from zrag.config.loader import load_config
        os.environ["TEST_HOST"] = "prod"
        _write_yaml(tmp_path, "h.yaml", 'host: "${TEST_HOST:-default}"')
        cfg = load_config(str(tmp_path))
        assert cfg["host"] == "prod"
        del os.environ["TEST_HOST"]

    def test_missing_no_default(self, tmp_path):
        """${VAR} 未定义且无默认值时抛 ValueError"""
        from zrag.config.loader import load_config
        _write_yaml(tmp_path, "k.yaml", 'key: "${UNDEF_VAR}"')
        with pytest.raises(ValueError, match="UNDEF_VAR"):
            load_config(str(tmp_path))
