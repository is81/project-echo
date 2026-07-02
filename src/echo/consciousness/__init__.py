"""双层意识架构 — 意识流 + 灵魂锚点 + 结晶引擎."""

from .anchors import SoulAnchor, AnchorRegistry, load_anchors_from_config
from .stream import ConsciousnessStream
from .crystallize import CrystallizationEngine

__all__ = [
    "SoulAnchor", "AnchorRegistry", "load_anchors_from_config",
    "ConsciousnessStream",
    "CrystallizationEngine",
]
