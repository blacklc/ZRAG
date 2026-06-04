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


class TestEnvOverride:
    """测试 5: 环境变量直接覆盖配置值"""

    def test_override_string(self, tmp_path):
        """字符串值被 LLM_GATEWAY_BASE_URL 覆盖"""
        os.environ["LLM_GATEWAY_BASE_URL"] = "http://docker:4000"
        _write_yaml(tmp_path, "t.yaml",
                     'llm:\n  gateway:\n    base_url: "http://localhost:4000"')
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        assert cfg["llm"]["gateway"]["base_url"] == "http://docker:4000"
        del os.environ["LLM_GATEWAY_BASE_URL"]

    def test_override_int(self, tmp_path):
        """整数值被 LLM_TIMEOUT 覆盖"""
        os.environ["LLM_TIMEOUT"] = "999"
        _write_yaml(tmp_path, "t.yaml", 'llm:\n  timeout: 200')
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        assert cfg["llm"]["timeout"] == 999
        assert isinstance(cfg["llm"]["timeout"], int)
        del os.environ["LLM_TIMEOUT"]

    def test_override_float(self, tmp_path):
        """浮点值被 COST_RATE 覆盖"""
        os.environ["COST_RATE"] = "1.5"
        _write_yaml(tmp_path, "t.yaml", 'cost:\n  rate: 0.5')
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        assert cfg["cost"]["rate"] == 1.5
        assert isinstance(cfg["cost"]["rate"], float)
        del os.environ["COST_RATE"]

    def test_override_bool_true(self, tmp_path):
        """bool 值被 DEBUG 覆盖 (true/1/yes 均视为 True)"""
        os.environ["DEBUG"] = "true"
        _write_yaml(tmp_path, "t.yaml", 'debug: False')
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        assert cfg["debug"] is True
        del os.environ["DEBUG"]

    def test_override_nonexistent(self, tmp_path):
        """不存在对应 env var 时保持 YAML 原值"""
        env_key = "NONEXISTENT_CFG_KEY"
        if env_key in os.environ:
            del os.environ[env_key]
        _write_yaml(tmp_path, "t.yaml", 'app:\n  name: "zrag"')
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        assert cfg["app"]["name"] == "zrag"

    def test_override_after_var_substitution(self, tmp_path):
        """env override 在 ${VAR} 解析后执行，可覆盖占位符结果"""
        os.environ["MY_DB"] = "yaml_val"
        os.environ["STORAGE_SQLITE_PATH"] = "env_override_val"
        _write_yaml(tmp_path, "t.yaml",
                     'storage:\n  sqlite_path: "${MY_DB}"')
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        # ${MY_DB} 先解析为 yaml_val，然后 STORAGE_SQLITE_PATH 覆盖为 env_override_val
        assert cfg["storage"]["sqlite_path"] == "env_override_val"
        del os.environ["MY_DB"]
        del os.environ["STORAGE_SQLITE_PATH"]

    def test_override_nested_key(self, tmp_path):
        """嵌套键按层级正确扁平化 (llm.gateway.model → LLM_GATEWAY_MODEL)"""
        os.environ["LLM_GATEWAY_MODEL"] = "gpt-4"
        _write_yaml(tmp_path, "t.yaml",
                     'llm:\n  gateway:\n    model: "smart-router"')
        from zrag.config.loader import load_config
        cfg = load_config(str(tmp_path))
        assert cfg["llm"]["gateway"]["model"] == "gpt-4"
        del os.environ["LLM_GATEWAY_MODEL"]
