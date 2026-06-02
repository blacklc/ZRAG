from pathlib import Path


def load_config(config_dir: str = "config") -> dict:
    """加载并合并配置文件中所有 YAML 文件

    扫描指定目录下所有 .yaml 文件，按 top-level key 进行深度合并。
    若多个文件存在相同 key，则按规则合并：dict 深度合并，非 dict 后覆盖前。
    合并完成后对配置项中的 ${ENV_VAR} 进行环境变量替换。

    @param config_dir: 配置文件的存放目录路径, defaults to "config"
    @type  config_dir: str, optional

    @raises: 当配置项中包含未定义的环境变量时抛出
    @type:   ValueError

    @return: 合并后的配置字典
    @type:   dict
    """
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
    """递归替换配置中所有 ${ENV_VAR} 为环境变量实际值

    遍历配置字典的每一项，若值为字符串则查找 ${VAR} 模式并替换为 os.environ 中的变量值。
    若某个环境变量未定义，则抛出 ValueError 并提示该变量名。
    若值为 dict，递归处理其子项。

    @param config: 需要执行环境变量替换的配置字典。该字典会被原地修改。
    @type  config: dict

    @raises: 当 ${VAR} 中的 VAR 在环境变量中不存在时抛出
    @type:   ValueError
    """
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
