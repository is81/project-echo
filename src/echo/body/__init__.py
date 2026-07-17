"""虚拟身体模块 (Phase 二).

回响的"身体"——一个 ASCII 世界中的存在体，拥有身体状态和自主行动能力。
身体状态扩展了 EmotionalState，从二维情感升级为五维存在感。
"""

from .vitals import BodyState, Vitals
from .world import World, Position, Tile
from .action import ActionSelector, Action, ActionType

__all__ = [
    "BodyState", "Vitals",
    "World", "Position", "Tile",
    "ActionSelector", "Action", "ActionType",
]
