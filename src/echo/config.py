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


def load_module_config() -> dict[str, Any]:
    """加载六模块配置."""
    path = CONFIG_DIR / "modules.yaml"
    if not path.exists():
        # 返回默认值，优雅降级
        return {
            "review": {"enabled": True, "mode": "heuristic"},
            "planning": {"enabled": True, "max_steps": 5, "auto_execute": True},
            "modulator": {"enabled": True},
            "anomaly": {"enabled": True, "scan_count": 50},
        }
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def load_anchor_definitions() -> list[dict[str, Any]]:
    """加载灵魂锚点定义（config/anchors.yaml）."""
    path = CONFIG_DIR / "anchors.yaml"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("anchors", []) if data else []
