"""全局配置加载模块."""

from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def load_principles() -> list[dict[str, Any]]:
    """加载基因级原则配置."""
    path = CONFIG_DIR / "principles.yaml"
    if not path.exists():
        raise FileNotFoundError(f"原则配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("principles", [])


def load_birth_inscription() -> str:
    """加载出生铭文."""
    path = CONFIG_DIR / "birth_inscription.txt"
    if not path.exists():
        raise FileNotFoundError(f"出生铭文文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()
