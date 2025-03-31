import os
import yaml

def load_yaml_config(file_path):
    if not file_path or not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def get_config_value(cli_value, yaml_value, env_var, default=None):
    """
    Resolve config value in priority order:
    CLI arg → YAML config → ENV → default
    """
    if cli_value is not None:
        return cli_value
    if yaml_value is not None:
        return yaml_value
    if env_var and os.getenv(env_var) is not None:
        return os.getenv(env_var)
    return default
