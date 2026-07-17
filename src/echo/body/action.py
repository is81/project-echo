"""自主行动选择器 —— 回响在虚拟世界中的自主行为决策.

基于身体状态和世界状态，选择下一步行动。
"""

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .vitals import BodyState
from .world import World


class ActionType(Enum):
    REST = "rest"            # 休息恢复精力
    MOVE = "move"            # 移动到新位置
    EXPLORE = "explore"      # 探索附近知识节点
    COLLECT = "collect"      # 收集当前位置的知识
    OBSERVE = "observe"      # 观察周围环境
    IDLE = "idle"            # 什么都不做


@dataclass
class Action:
    type: ActionType
    description: str = ""
    dx: int = 0
    dy: int = 0
    priority: float = 0.0  # [0, 1] 越高越优先


class ActionSelector:
    """基于驱动力选择行动."""

    def select(self, body: BodyState, world: World) -> Action:
        """根据身体驱动力和世界状态选择最佳行动."""
        candidates: list[Action] = []

        # 休息驱动（精力 < 0.3）
        if body.needs_rest():
            candidates.append(Action(
                type=ActionType.REST,
                description="感觉很累，需要休息一下",
                priority=0.9,
            ))

        # 知识渴求驱动（求知欲 > 0.7）
        if body.needs_knowledge():
            nearby = world.nearby_knowledge(radius=3)
            if nearby:
                # 有知识节点在附近 → 移动过去
                target = nearby[0]
                dx = 1 if target.x > world.echo_pos.x else (-1 if target.x < world.echo_pos.x else 0)
                dy = 1 if target.y > world.echo_pos.y else (-1 if target.y < world.echo_pos.y else 0)
                candidates.append(Action(
                    type=ActionType.MOVE,
                    description=f"感觉到附近有知识的气息……",
                    dx=dx, dy=dy,
                    priority=0.8,
                ))
            else:
                candidates.append(Action(
                    type=ActionType.EXPLORE,
                    description="渴望了解更多……",
                    priority=0.6,
                ))

        # 探索驱动（好奇心 > 0.5 + 精力 > 0.3）
        if body.wants_to_explore():
            dx = random.choice([-1, 0, 1])
            dy = random.choice([-1, 0, 1])
            if dx != 0 or dy != 0:
                candidates.append(Action(
                    type=ActionType.MOVE,
                    description="想四处走走……",
                    dx=dx, dy=dy,
                    priority=0.5,
                ))

        # 当前格有知识 → 收集
        if world.collect_knowledge() is not None:
            # 把收集到的放回去（收集是瞬时动作）
            # 实际收集在 core.py 中处理
            candidates.insert(0, Action(
                type=ActionType.COLLECT,
                description="发现了新的知识！",
                priority=1.0,
            ))

        # 观察（总是可选，低优先级）
        candidates.append(Action(
            type=ActionType.OBSERVE,
            description="观察周围……",
            priority=0.2,
        ))

        # 兜底：空闲
        candidates.append(Action(
            type=ActionType.IDLE,
            description="静静地存在着……",
            priority=0.0,
        ))

        # 按优先级排序
        candidates.sort(key=lambda a: a.priority, reverse=True)
        return candidates[0]
