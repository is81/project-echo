"""规划模块 (Prefrontal Cortex) —— 将模糊目标分解为清晰行动步骤.

语言模块理解意图，规划模块决定"怎么做"。
规划不负责执行——执行交给工具模块。
"""

from .planner import PlanEngine, Plan, Step, PlanResult

__all__ = ["PlanEngine", "Plan", "Step", "PlanResult"]
