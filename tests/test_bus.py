"""认知总线测试 —— 验证 ModuleBus 模块协调能力."""

import pytest
from echo.bus import ModuleBus, ModuleInfo


class MockModule:
    """模拟一个认知模块."""
    def __init__(self, name="mock"):
        self.name = name
        self.woken = False
        self.tick_count = 0
        self.closed = False
        self.last_signal = None

    def wake(self):
        self.woken = True

    def tick(self):
        self.tick_count += 1

    def sleep(self):
        self.closed = True

    def close(self):
        self.closed = True


class TestModuleInfo:
    """测试 ModuleInfo 数据类."""

    def test_default_info(self):
        info = ModuleInfo(name="test", instance=MockModule())
        assert info.name == "test"
        assert info.category == "cognitive"
        assert info.enabled is True
        assert info.tick_count == 0
        assert info.error_count == 0

    def test_tick_increments_counter(self):
        mod = MockModule()
        info = ModuleInfo(name="test", instance=mod)
        info.tick()
        assert info.tick_count == 1

    def test_disabled_module_tick_skips(self):
        mod = MockModule()
        info = ModuleInfo(name="test", instance=mod, enabled=False)
        result = info.tick()
        assert result is True  # skip is not an error
        assert info.tick_count == 0  # not incremented


class TestModuleBus:
    """测试认知总线."""

    def test_register_module(self):
        bus = ModuleBus()
        mod = MockModule()
        bus.register("linguistic", mod, category="cognitive")
        assert bus.get("linguistic") is mod

    def test_get_nonexistent_returns_none(self):
        bus = ModuleBus()
        assert bus.get("nonexistent") is None

    def test_list_modules(self):
        bus = ModuleBus()
        bus.register("linguistic", MockModule(), category="cognitive")
        bus.register("memory", MockModule(), category="cognitive")
        modules = bus.list_modules()
        assert len(modules) == 2
        names = [m["name"] for m in modules]
        assert "linguistic" in names
        assert "memory" in names

    def test_wake_all_calls_wake(self):
        bus = ModuleBus()
        mod = MockModule()
        bus.register("linguistic", mod)
        bus.wake_all()
        assert mod.woken is True

    def test_wake_all_handles_errors(self):
        """一个模块唤醒失败不应阻塞其他模块."""
        bus = ModuleBus()
        good = MockModule(name="good")

        class BadModule:
            def wake(self):
                raise RuntimeError("failed to wake")

        bus.register("good", good)
        bus.register("bad", BadModule())
        bus.wake_all()

        assert good.woken is True
        modules = bus.list_modules()
        bad_info = [m for m in modules if m["name"] == "bad"][0]
        assert bad_info["enabled"] is False

    def test_tick_all_counts(self):
        bus = ModuleBus()
        mod1 = MockModule()
        mod2 = MockModule()
        bus.register("mod1", mod1)
        bus.register("mod2", mod2)
        bus.wake_all()

        results = bus.tick_all()
        assert results["ok"] == 2
        assert mod1.tick_count == 1
        assert mod2.tick_count == 1

    def test_tick_all_handles_errors(self):
        """一个模块 tick 失败不应阻塞其他模块."""
        bus = ModuleBus()
        good = MockModule(name="good")

        class CrashyModule:
            def tick(self):
                raise RuntimeError("crash")

        bus.register("good", good)
        bus.register("crashy", CrashyModule())
        bus.wake_all()

        results = bus.tick_all()
        assert results["failed"] >= 1
        assert results["ok"] >= 1
        assert good.tick_count == 1  # good module still ticked

    def test_shutdown_calls_sleep_or_close(self):
        bus = ModuleBus()
        mod1 = MockModule(name="mod1")
        mod2 = MockModule(name="mod2")

        bus.register("mod1", mod1)
        bus.register("mod2", mod2)
        bus.wake_all()
        bus.shutdown()

        # Both modules should have been shut down (sleep was called)
        assert mod1.closed is True
        assert mod2.closed is True

    def test_signal_routing(self):
        bus = ModuleBus()
        received = []

        def handler(**kwargs):
            received.append(kwargs)

        bus.subscribe("emotion.changed", handler)
        responses = bus.signal("emotion.changed", valence=0.5, arousal=0.3)

        assert len(received) == 1
        assert received[0]["valence"] == 0.5
        assert received[0]["arousal"] == 0.3

    def test_wildcard_signal_matching(self):
        bus = ModuleBus()
        received = []

        def handler(**kwargs):
            received.append(kwargs)

        bus.subscribe("emotion.*", handler)
        bus.signal("emotion.changed", valence=0.5, arousal=0.3)
        bus.signal("emotion.regressed", valence=0.0)

        assert len(received) == 2

    def test_signal_handler_error_isolated(self):
        bus = ModuleBus()
        good_received = []

        def bad_handler(**kwargs):
            raise RuntimeError("bad handler")

        def good_handler(**kwargs):
            good_received.append(True)

        bus.subscribe("test.signal", bad_handler)
        bus.subscribe("test.signal", good_handler)
        bus.signal("test.signal")

        assert len(good_received) == 1  # good handler still ran

    def test_status(self):
        bus = ModuleBus()
        bus.register("linguistic", MockModule(), category="cognitive")
        bus.register("emotion", MockModule(), category="consciousness")
        bus.wake_all()

        status = bus.status()
        assert status["status"] == "running"
        assert status["module_count"] == 2
        assert len(status["modules"]) == 2

    def test_is_running(self):
        bus = ModuleBus()
        assert not bus.is_running
        bus.wake_all()
        assert bus.is_running
        bus.shutdown()
        assert not bus.is_running

    def test_multiple_registrations(self):
        """注册 8 个模块（真实场景）."""
        bus = ModuleBus()
        categories = {
            "linguistic": "cognitive",
            "memory": "cognitive",
            "tools": "cognitive",
            "review": "cognitive",
            "planning": "cognitive",
            "emotion": "consciousness",
            "consciousness": "consciousness",
            "anchors": "consciousness",
        }
        for name, cat in categories.items():
            bus.register(name, MockModule(name=name), category=cat)

        bus.wake_all()
        status = bus.status()
        assert status["module_count"] == 8

        results = bus.tick_all()
        assert results["ok"] == 8

        bus.shutdown()
        assert not bus.is_running

    def test_on_emotion_changed_event(self):
        bus = ModuleBus()
        events = []

        class MockEmotion:
            def __init__(self, v, a):
                self.valence = v
                self.arousal = a

            @property
            def mood_label(self):
                return "excited" if self.arousal > 0.5 else "calm"

        bus.subscribe("emotion.changed", lambda **kw: events.append(kw))
        emotion = MockEmotion(0.7, 0.8)
        responses = bus.on_emotion_changed(emotion)

        assert len(events) == 1
        assert events[0]["valence"] == 0.7
        assert events[0]["mood"] == "excited"

    def test_on_response_generated_event(self):
        bus = ModuleBus()
        reviewed = []

        def review_handler(**kwargs):
            reviewed.append(kwargs)
            return {"verdict": "pass"}

        bus.subscribe("response.generated", review_handler)
        responses = bus.on_response_generated("你好！", "你好")

        assert len(reviewed) == 1
        assert len(responses) == 1
        assert responses[0]["verdict"] == "pass"
