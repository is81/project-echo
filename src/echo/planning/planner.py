"""规划引擎 —— 目标→行动步骤分解.

使用思维链 prompt 让现有 LLM 输出 JSON 格式的行动计划。
不引入新模型——轻量级规则引擎 + LLM prompt 工程。

数据流:
  用户意图 → PlanEngine.plan() → Plan(Step[]) → 工具模块执行
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("echo.planning")


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    """行动计划中的单个步骤."""
    id: str                          # 步骤 ID（如 "step-1"）
    description: str                 # 人类可读的描述
    tool_name: Optional[str] = None  # 使用的工具名（None = 思考步骤）
    tool_args: dict = field(default_factory=dict)  # 工具参数
    depends_on: list[str] = field(default_factory=list)  # 依赖的步骤 ID
    status: StepStatus = StepStatus.PENDING
    result: str = ""                 # 执行结果
    review_pass: bool = True         # 审查是否通过

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result,
        }


@dataclass
class Plan:
    """完整的行动计划."""
    goal: str                        # 用户原始目标
    decomposed_goal: str = ""        # 分解后的问题描述
    steps: list[Step] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0

    def progress(self) -> float:
        """返回执行进度 [0, 1]."""
        if not self.steps:
            return 1.0
        done = sum(1 for s in self.steps
                   if s.status in (StepStatus.DONE, StepStatus.SKIPPED))
        return done / len(self.steps)

    def next_pending(self) -> Optional[Step]:
        """返回下一个可执行的步骤（依赖已满足）."""
        done_ids = {s.id for s in self.steps
                    if s.status in (StepStatus.DONE, StepStatus.SKIPPED)}
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            # 检查所有依赖是否已完成
            if all(dep in done_ids for dep in step.depends_on):
                return step
        return None

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "decomposed_goal": self.decomposed_goal,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "progress": f"{self.progress():.0%}",
        }


@dataclass
class PlanResult:
    """规划执行结果."""
    plan: Plan
    final_answer: str = ""           # 最终回复（由语言模块生成）
    tools_called: int = 0
    steps_completed: int = 0
    steps_failed: int = 0


class PlanEngine:
    """规划引擎 —— 回响的"前额叶".

    将模糊的用户请求分解为可执行的具体步骤。

    使用方式:
        engine = PlanEngine(llm_backend, available_tools)
        plan = engine.decompose("帮我优化记忆检索速度")
        # → Plan with steps like: 1. read_file 2. analyze 3. propose solutions
    """

    # LLM prompt 模板 —— 让语言模块输出 JSON 行动计划
    PLANNING_SYSTEM_PROMPT = """你是一个任务规划器。你的职责是将用户的目标分解为具体的行动步骤。

可用工具列表：
{tools_list}

请将目标分解为 2-5 个步骤。每个步骤可以是一个工具调用或一个思考步骤。

输出格式必须严格为 JSON：
```json
{{
  "decomposed_goal": "将用户目标重新表述为清晰的问题描述",
  "steps": [
    {{
      "id": "step-1",
      "description": "这个步骤做什么（用中文描述）",
      "tool_name": "工具名（如果不需要工具则为 null）",
      "tool_args": {{"参数名": "参数值"}},
      "depends_on": []
    }},
    {{
      "id": "step-2",
      "description": "下一个步骤",
      "tool_name": null,
      "tool_args": {{}},
      "depends_on": ["step-1"]
    }}
  ]
}}
```

规划原则：
1. 步骤之间如果有依赖关系，用 depends_on 标注
2. 优先使用可用工具，避免虚构不存在的工具
3. 如果用户目标本身很清晰/简单，1-2 步即可，不要过度分解
4. 思考步骤（tool_name=null）用于分析结果、对比方案
5. 最后一步应生成一个可直接回复用户的结论"""

    def __init__(self, llm_backend=None, available_tools: list[dict] = None):
        """初始化规划引擎.

        Args:
            llm_backend: LLM 后端（用于智能分解）
            available_tools: 可用工具列表 [{"name": "...", "description": "..."}, ...]
        """
        self._llm = llm_backend
        self._tools = available_tools or []

    def decompose(self, goal: str, context: str = "") -> Plan:
        """将目标分解为行动步骤.

        Args:
            goal: 用户目标描述
            context: 可选的额外上下文（记忆、系统状态等）

        Returns:
            Plan: 包含分解后的步骤列表
        """
        plan = Plan(goal=goal)

        # 策略 1: 如果用户目标是明确的工具调用，跳过分解
        direct_tool = self._match_direct_tool(goal)
        if direct_tool:
            plan.steps = [
                Step(
                    id="step-1",
                    description=f"执行: {goal}",
                    tool_name=direct_tool["name"],
                    tool_args=direct_tool.get("args", {}),
                ),
                Step(
                    id="step-2",
                    description="整理结果并回复用户",
                    tool_name=None,
                    tool_args={},
                    depends_on=["step-1"],
                ),
            ]
            plan.decomposed_goal = goal
            plan.total_steps = 2
            return plan

        # 策略 2: 使用 LLM 智能分解
        if self._llm:
            llm_plan = self._llm_decompose(goal, context)
            if llm_plan and llm_plan.steps:
                return llm_plan

        # 策略 3: 兜底 —— 单步"思考+回复"
        plan.decomposed_goal = goal
        plan.steps = [
            Step(
                id="step-1",
                description=f"思考: {goal}",
                tool_name=None,
                tool_args={},
            ),
        ]
        plan.total_steps = 1
        return plan

    def _match_direct_tool(self, goal: str) -> Optional[dict]:
        """检查目标是否直接匹配某个工具的能力."""
        if not self._tools:
            return None

        goal_lower = goal.lower()

        # 常见意图→工具映射
        intent_tool_map = {
            "搜索": "search_web",
            "查": "search_web",
            "找": "search_memory",
            "读": "read_file",
            "写": "write_file",
            "运行": "run_command",
            "执行": "run_command",
            "看看": "list_files",
            "列出": "list_files",
            "现在几点": "get_time",
            "状态": "get_status",
            "记忆": "search_memory",
            "时间": "get_time",
        }

        for intent, tool_name in intent_tool_map.items():
            if intent in goal_lower:
                # 找到匹配的工具定义
                tool_def = next((t for t in self._tools if t.get("name") == tool_name), None)
                if tool_def:
                    return {"name": tool_name, "args": {}}

        return None

    def _llm_decompose(self, goal: str, context: str = "") -> Optional[Plan]:
        """使用 LLM 将目标分解为步骤."""
        tools_desc = "\n".join(
            f"- {t.get('name', '?')}: {t.get('description', '无描述')}"
            for t in self._tools
        ) if self._tools else "（无可用工具）"

        prompt = (
            f"用户目标: {goal}\n"
            + (f"背景上下文: {context}\n" if context else "")
            + f"\n请将这个目标分解为具体的行动步骤。"
        )

        try:
            response = self._llm.generate(
                prompt=prompt,
                system_prompt=self.PLANNING_SYSTEM_PROMPT.format(
                    tools_list=tools_desc
                ),
                temperature=0.1,  # 低温——规划需要精确而非创意
            )

            if not response.text:
                return None

            # 解析 JSON
            plan_data = self._parse_plan_json(response.text)
            if not plan_data:
                return None

            plan = Plan(
                goal=goal,
                decomposed_goal=plan_data.get("decomposed_goal", goal),
            )

            steps_data = plan_data.get("steps", [])
            for sd in steps_data:
                step = Step(
                    id=sd.get("id", f"step-{len(plan.steps)+1}"),
                    description=sd.get("description", ""),
                    tool_name=sd.get("tool_name"),
                    tool_args=sd.get("tool_args", {}),
                    depends_on=sd.get("depends_on", []),
                )
                plan.steps.append(step)

            plan.total_steps = len(plan.steps)
            return plan

        except Exception as e:
            logger.warning(f"LLM 规划失败: {e}")
            return None

    def _parse_plan_json(self, text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON 计划."""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取 { ... } 块
        brace_match = re.search(r'\{.*"steps".*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.debug(f"无法解析 LLM 规划输出: {text[:200]}...")
        return None

    def execute_step(self, step: Step, tool_executor=None) -> str:
        """执行单个规划步骤.

        Args:
            step: 要执行的步骤
            tool_executor: 工具执行函数 (tool_name, tool_args) -> result_text

        Returns:
            步骤执行结果文本
        """
        if step.tool_name and tool_executor:
            try:
                result = tool_executor(step.tool_name, step.tool_args)
                step.status = StepStatus.DONE
                step.result = result
                return result
            except Exception as e:
                step.status = StepStatus.FAILED
                step.result = str(e)
                return f"步骤失败: {e}"
        else:
            # 思考步骤——标记完成，不执行任何工具
            step.status = StepStatus.DONE
            step.result = f"[思考] {step.description}"
            return step.result
