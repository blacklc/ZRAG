from pathlib import Path


def load_config(config_dir: str = "config") -> dict:
    """扫描目录下所有 .yaml 文件，按 top-level key 深度合并"""
    config = {}
    config_path = Path(config_dir)
    if not config_path.exists():
        return config
    for yaml_file in sorted(config_path.glob("*.yaml")):
        data = _yaml.safe_load(yaml_file.read_text())
        if not data:
            continue
        for key, value in data.items():
            if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                config[key] = {**config[key], **value}
            else:
                config[key] = value
    _resolve_env_vars(config)
    return config


def _resolve_env_vars(config: dict) -> None:
    """递归替换 dict 中所有 `${ENV_VAR}` 为环境变量值"""
    import os as _os
    import re as _re

    pattern = _re.compile(r'\$\{(\w+)\}')

    def _resolve(value):
        if isinstance(value, str):
            def _replace(m):
                var_name = m.group(1)
                env_val = _os.environ.get(var_name)
                if env_val is None:
                    raise ValueError(f"环境变量 {var_name} 未定义")
                return env_val
            return pattern.sub(_replace, value)
        if isinstance(value, dict):
            return {k: _resolve(v) for k, v in value.items()}
        return value

    for key in list(config.keys()):
        config[key] = _resolve(config[key])


try:
    import yaml as _yaml
except ImportError:
    import warnings as _w
    _w.warn("PyYAML not installed; load_config will fail at runtime")
    _yaml = None
