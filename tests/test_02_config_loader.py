"""切片 1 — 配置加载器"""
import tempfile
from pathlib import Path


class TestSingleYaml:
    def test_load_single_file(self):
        """单个 YAML 文件 → 返回正确键值"""
        from zrag.config.loader import load_config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'test.yaml').write_text('key: value\nnum: 42')
            config = load_config(tmp)
            assert config == {'key': 'value', 'num': 42}


class TestEmptyDir:
    def test_empty_directory(self):
        """空目录 → 返回空 dict"""
        from zrag.config.loader import load_config
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(tmp)
            assert config == {}

    def test_nonexistent_directory(self):
        """不存在的目录 → 返回空 dict"""
        from zrag.config.loader import load_config
        config = load_config('/tmp/nonexistent_zrag_dir_xyz')
        assert config == {}


class TestMerge:
    def test_multiple_files_different_keys(self):
        """多个文件不同 key → 合并"""
        from zrag.config.loader import load_config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'a.yaml').write_text('key1: val1')
            (Path(tmp) / 'b.yaml').write_text('key2: val2')
            config = load_config(tmp)
            assert config == {'key1': 'val1', 'key2': 'val2'}

    def test_same_key_dict_deep_merge(self):
        """多个文件相同 key 且都是 dict → 深度合并"""
        from zrag.config.loader import load_config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'a.yaml').write_text('llm:\n  provider: gateway\n  timeout: 30')
            (Path(tmp) / 'b.yaml').write_text('llm:\n  model: smart-router')
            config = load_config(tmp)
            assert config == {'llm': {'provider': 'gateway', 'timeout': 30, 'model': 'smart-router'}}

    def test_same_key_non_dict_overrides(self):
        """多个文件相同 key 非 dict → 后覆盖前"""
        from zrag.config.loader import load_config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'a.yaml').write_text('debug: true')
            (Path(tmp) / 'b.yaml').write_text('debug: false')
            config = load_config(tmp)
            assert config == {'debug': False}


class TestEmptyFile:
    def test_empty_yaml_skipped(self):
        """空 YAML 文件被跳过"""
        from zrag.config.loader import load_config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'empty.yaml').write_text('')
            config = load_config(tmp)
            assert config == {}


class TestEnvVar:
    def test_env_var_resolved(self):
        """${VAR} → 替换为环境变量实际值"""
        import os
        from zrag.config.loader import load_config
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'env.yaml').write_text('api_key: ${TEST_ZRAG_API}')
            os.environ['TEST_ZRAG_API'] = 'sk-test-key'
            config = load_config(tmp)
            assert config == {'api_key': 'sk-test-key'}

    def test_env_var_undefined_raises(self):
        """${UNDEFINED} → 抛 ValueError"""
        from zrag.config.loader import load_config
        import pytest
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'bad.yaml').write_text('key: ${NO_SUCH_VAR_12345}')
            with pytest.raises(ValueError, match='NO_SUCH_VAR_12345'):
                load_config(tmp)
