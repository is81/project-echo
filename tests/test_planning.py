"""规划模块测试 —— 验证 Prefrontal Cortex 的任务分解能力."""

import pytest
from echo.planning.planner import (
    PlanEngine, Plan, Step, StepStatus, PlanResult,
)


class TestStep:
    """测试 Step 数据类."""

    def test_default_step(self):
        step = Step(id="step-1", description="测试步骤")
        assert step.status == StepStatus.PENDING
        assert step.tool_name is None
        assert step.depends_on == []
        assert step.result == ""

    def test_step_with_tool(self):
        step = Step(
            id="step-1",
            description="读文件",
            tool_name="read_file",
            tool_args={"path": "test.md"},
        )
        assert step.tool_name == "read_file"
        assert step.tool_args["path"] == "test.md"

    def test_step_dependencies(self):
        step = Step(
            id="step-3",
            description="总结结果",
            depends_on=["step-1", "step-2"],
        )
        assert len(step.depends_on) == 2

    def test_step_to_dict(self):
        step = Step(id="s1", description="测试", tool_name="search_web")
        d = step.to_dict()
        assert d["id"] == "s1"
        assert d["tool_name"] == "search_web"
        assert d["status"] == "pending"


class TestPlan:
    """测试 Plan —— 完整行动计划."""

    def test_empty_plan(self):
        plan = Plan(goal="测试")
        assert plan.progress() == 1.0
        assert plan.next_pending() is None

    def test_plan_with_steps(self):
        step1 = Step(id="step-1", description="第一步")
        step2 = Step(id="step-2", description="第二步", depends_on=["step-1"])
        plan = Plan(goal="测试多步", steps=[step1, step2], total_steps=2)

        # 第一步应该是下一个 pending（没有依赖）
        next_step = plan.next_pending()
        assert next_step is not None
        assert next_step.id == "step-1"

    def test_plan_dependency_resolution(self):
        """依赖满足后才释放下一步."""
        step1 = Step(id="step-1", description="第一步")
        step2 = Step(id="step-2", description="第二步", depends_on=["step-1"])
        step3 = Step(id="step-3", description="第三步", depends_on=["step-2"])
        plan = Plan(goal="依赖链", steps=[step1, step2, step3], total_steps=3)

        # 初始：step-1 可用
        assert plan.next_pending().id == "step-1"

        # 完成 step-1
        step1.status = StepStatus.DONE
        assert plan.next_pending().id == "step-2"

        # step-2 还在 pending，step-3 不可用
        assert plan.next_pending().id == "step-2"

        # 完成 step-2
        step2.status = StepStatus.DONE
        assert plan.next_pending().id == "step-3"

    def test_plan_progress_tracking(self):
        step1 = Step(id="step-1", description="第一步")
        step2 = Step(id="step-2", description="第二步")
        plan = Plan(goal="进度", steps=[step1, step2], total_steps=2)

        assert plan.progress() == 0.0

        step1.status = StepStatus.DONE
        assert plan.progress() == 0.5

        step2.status = StepStatus.SKIPPED
        assert plan.progress() == 1.0

    def test_plan_to_dict(self):
        step = Step(id="step-1", description="测试")
        plan = Plan(goal="目标", steps=[step], total_steps=1)
        d = plan.to_dict()
        assert d["goal"] == "目标"
        assert len(d["steps"]) == 1
        assert "progress" in d


class TestPlanEngine:
    """测试 PlanEngine."""

    @pytest.fixture
    def sample_tools(self):
        return [
            {"name": "read_file", "description": "读取文件内容"},
            {"name": "search_web", "description": "搜索互联网"},
            {"name": "search_memory", "description": "搜索回响的记忆"},
            {"name": "list_files", "description": "列出文件"},
            {"name": "get_time", "description": "获取当前时间"},
            {"name": "get_status", "description": "检查回响状态"},
            {"name": "run_command", "description": "运行终端命令"},
        ]

    def test_engine_initialization(self, sample_tools):
        """引擎应该可以无 LLM 初始化."""
        engine = PlanEngine(available_tools=sample_tools)
        assert engine._llm is None
        assert len(engine._tools) == 7

    def test_decompose_simple_without_llm(self, sample_tools):
        """无 LLM 时，简单目标返回单步计划."""
        engine = PlanEngine(available_tools=sample_tools)
        plan = engine.decompose("现在几点")

        assert plan is not None
        assert plan.goal == "现在几点"
        # 应该匹配到 get_time 工具
        assert plan.total_steps >= 1
        assert any(s.tool_name == "get_time" for s in plan.steps)

    def test_decompose_search_intent(self, sample_tools):
        """搜索意图应该匹配到对应工具."""
        engine = PlanEngine(available_tools=sample_tools)
        plan = engine.decompose("帮我搜索一下 Python 协程")

        assert plan is not None
        assert any(s.tool_name == "search_web" for s in plan.steps)

    def test_decompose_fallback_for_unknown(self, sample_tools):
        """未知意图应该有兜底计划（不崩溃）."""
        engine = PlanEngine(available_tools=sample_tools)
        plan = engine.decompose("帮我思考人生的意义")

        assert plan is not None
        assert plan.total_steps >= 1
        # 兜底: 至少有一个思考步骤
        assert len(plan.steps) > 0

    def test_execute_step_with_tool(self, sample_tools):
        """执行工具步骤."""
        engine = PlanEngine(available_tools=sample_tools)
        step = Step(
            id="step-1",
            description="读文件",
            tool_name="read_file",
            tool_args={"path": "test.md"},
        )

        def mock_executor(tool_name, tool_args):
            return f"文件内容: {tool_args.get('path')}"

        result = engine.execute_step(step, mock_executor)
        assert "test.md" in result
        assert step.status == StepStatus.DONE

    def test_execute_step_failure_handled(self, sample_tools):
        """工具执行失败不应该崩溃."""
        engine = PlanEngine(available_tools=sample_tools)
        step = Step(
            id="step-1",
            description="会失败的步骤",
            tool_name="bad_tool",
            tool_args={},
        )

        def mock_executor(tool_name, tool_args):
            raise RuntimeError("工具崩溃了")

        result = engine.execute_step(step, mock_executor)
        assert step.status == StepStatus.FAILED
        assert "失败" in result

    def test_execute_think_step(self, sample_tools):
        """思考步骤应该标记完成但不调用工具."""
        engine = PlanEngine(available_tools=sample_tools)
        step = Step(id="step-1", description="思考一下", tool_name=None)

        call_count = 0
        def mock_executor(tool_name, tool_args):
            nonlocal call_count
            call_count += 1
            return "called"

        result = engine.execute_step(step, mock_executor)
        assert step.status == StepStatus.DONE
        assert call_count == 0  # 思考步骤不调用工具

    def test_decompose_complex_goal_fallback(self, sample_tools):
        """复杂目标（无 LLM）应该有合理的兜底."""
        engine = PlanEngine(available_tools=sample_tools)
        plan = engine.decompose("这是一个非常复杂且没有匹配任何工具的目标")

        assert plan is not None
        assert plan.total_steps == 1
        assert plan.steps[0].tool_name is None  # 思考步骤

    def test_intent_tool_map_coverage(self, sample_tools):
        """每个意图关键词都应该匹配到正确的工具."""
        engine = PlanEngine(available_tools=sample_tools)

        test_cases = [
            ("搜索 Python 教程", "search_web"),
            ("找一下之前的记忆", "search_memory"),
            ("现在几点了", "get_time"),
            ("看看文件", "list_files"),
            ("读取 README", "read_file"),
            ("运行测试", "run_command"),
        ]

        for goal, expected_tool in test_cases:
            plan = engine.decompose(goal)
            assert any(s.tool_name == expected_tool for s in plan.steps), \
                f"目标 '{goal}' 应该匹配工具 '{expected_tool}'，实际步骤: {[s.tool_name for s in plan.steps]}"


class TestPlanResult:
    """测试 PlanResult."""

    def test_result_tracks_stats(self):
        plan = Plan(goal="测试", total_steps=3)
        result = PlanResult(
            plan=plan,
            tools_called=2,
            steps_completed=2,
            steps_failed=1,
        )
        assert result.tools_called == 2
        assert result.steps_completed == 2
        assert result.steps_failed == 1


class TestStepStatus:
    """测试 StepStatus 枚举."""

    def test_all_statuses(self):
        statuses = list(StepStatus)
        assert StepStatus.PENDING in statuses
        assert StepStatus.RUNNING in statuses
        assert StepStatus.DONE in statuses
        assert StepStatus.FAILED in statuses
        assert StepStatus.SKIPPED in statuses
