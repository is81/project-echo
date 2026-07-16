"""认知总线 — Echo 的模块协调层.

将 Echo 从"上帝对象"重构为"协调总线"：
  - 六个认知模块注册到总线
  - 每个模块有自己的生命周期（tick）
  - 总线处理模块间信号路由
  - 模块是独立单元，Echo 只是 conductor

生命周期的三个节点:
  wake  → 注册所有模块 + 初始化
  tick  → 每次交互后更新模块状态
  sleep → 关闭模块 + 持久化
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("echo.bus")


@dataclass
class ModuleInfo:
    """总线上注册的模块信息."""
    name: str                          # 模块名（如 "linguistic", "memory"）
    instance: Any                      # 模块实例
    category: str = "cognitive"        # 类别: cognitive | support | consciousness
    enabled: bool = True               # 是否激活
    tick_count: int = 0               # tick 计数
    error_count: int = 0              # 错误计数
    last_error: Optional[str] = None  # 上次错误消息

    def tick(self) -> bool:
        """执行模块的一次维护周期. 返回是否成功."""
        if not self.enabled:
            return True
        try:
            self.tick_count += 1
            return True
        except Exception as e:
            self.error_count += 1
            self.last_error = str(e)
            logger.warning(f"模块 [{self.name}] tick 异常: {e}")
            return False


class ModuleBus:
    """认知总线 — 模块注册、信号路由、生命周期管理.

    使用方式:
        bus = ModuleBus()

        # wake 阶段: 注册所有模块
        bus.register("linguistic", llm_backend, category="cognitive")
        bus.register("memory", memory_store, category="cognitive")

        # 运行时: 信号路由
        bus.signal("review.critique", draft=draft, context=...)

        # sleep 阶段: 关闭所有模块
        bus.shutdown()
    """

    def __init__(self):
        self._modules: dict[str, ModuleInfo] = {}
        self._signals: dict[str, list[Callable]] = {}
        self._session_start: float = 0.0
        self._total_ticks: int = 0
        self._status: str = "initialized"

    # ── 模块注册 ──

    def register(self, name: str, instance: Any,
                 category: str = "cognitive") -> "ModuleBus":
        """注册一个模块到总线."""
        if name in self._modules:
            logger.warning(f"模块 [{name}] 已注册，将被覆盖")
        self._modules[name] = ModuleInfo(
            name=name,
            instance=instance,
            category=category,
        )
        logger.info(f"模块 [{name}] 已注册 (category={category})")
        return self

    def get(self, name: str) -> Optional[Any]:
        """获取模块实例."""
        info = self._modules.get(name)
        return info.instance if info and info.enabled else None

    def list_modules(self) -> list[dict]:
        """列出所有注册模块."""
        return [
            {
                "name": m.name,
                "category": m.category,
                "enabled": m.enabled,
                "tick_count": m.tick_count,
                "error_count": m.error_count,
            }
            for m in self._modules.values()
        ]

    # ── 生命周期 ──

    def wake_all(self) -> None:
        """唤醒所有模块（启动时调用）."""
        self._status = "waking"
        self._session_start = __import__("time").time()

        for name, info in self._modules.items():
            try:
                if hasattr(info.instance, "wake"):
                    info.instance.wake()
                info.enabled = True
            except Exception as e:
                logger.error(f"模块 [{name}] 唤醒失败: {e}")
                info.enabled = False
                info.last_error = str(e)

        self._status = "running"
        modules_str = ", ".join(
            f"{m.name}({m.category})" for m in self._modules.values()
        )
        logger.info(f"总线已启动。模块: [{modules_str}]")

    def tick_all(self) -> dict:
        """所有模块执行一次 tick（每次交互后调用）."""
        self._total_ticks += 1
        results = {"ok": 0, "failed": 0, "skipped": 0}

        for name, info in self._modules.items():
            if not info.enabled:
                results["skipped"] += 1
                continue

            # 各模块的 tick 逻辑
            try:
                if hasattr(info.instance, "tick"):
                    info.instance.tick()
                results["ok"] += 1
            except Exception as e:
                results["failed"] += 1
                info.error_count += 1
                info.last_error = str(e)
                logger.warning(f"模块 [{name}] tick 失败: {e}")

        return results

    def shutdown(self) -> None:
        """关闭所有模块（退出时调用）."""
        self._status = "shutting_down"

        for name, info in self._modules.items():
            try:
                if hasattr(info.instance, "sleep"):
                    info.instance.sleep()
                elif hasattr(info.instance, "close"):
                    info.instance.close()
            except Exception as e:
                logger.warning(f"模块 [{name}] shutdown 异常: {e}")

        self._status = "stopped"
        logger.info(
            f"总线已关闭。共 {self._total_ticks} ticks, "
            f"{len(self._modules)} 模块"
        )

    # ── 信号路由 ──

    def signal(self, signal_name: str, **kwargs) -> list[Any]:
        """向所有订阅了该信号的模块发送消息.

        Args:
            signal_name: 信号名（如 "review.critique", "emotion.changed"）
            **kwargs: 信号参数

        Returns:
            各模块的响应列表
        """
        responses = []
        handlers = self._signals.get(signal_name, [])

        # 也匹配通配符订阅（如 "review.*"）
        for pattern, pattern_handlers in self._signals.items():
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if signal_name.startswith(prefix):
                    handlers.extend(pattern_handlers)

        for handler in handlers:
            try:
                result = handler(**kwargs)
                if result is not None:
                    responses.append(result)
            except Exception as e:
                logger.warning(f"信号 [{signal_name}] 处理异常: {e}")

        return responses

    def subscribe(self, signal_name: str, handler: Callable) -> None:
        """订阅一个信号."""
        if signal_name not in self._signals:
            self._signals[signal_name] = []
        self._signals[signal_name].append(handler)

    # ── 跨模块事件 ──

    def on_emotion_changed(self, emotional_state) -> list[Any]:
        """情绪变化事件 → 通知所有关心该信号的模块."""
        return self.signal(
            "emotion.changed",
            valence=emotional_state.valence,
            arousal=emotional_state.arousal,
            mood=emotional_state.mood_label,
        )

    def on_response_generated(self, draft: str, user_input: str) -> list[Any]:
        """回应生成事件 → 审查模块介入."""
        return self.signal(
            "response.generated",
            draft=draft,
            user_input=user_input,
        )

    def on_knowledge_extracted(self, facts: list[str], source: str) -> list[Any]:
        """知识提取事件 → 记忆模块记录."""
        return self.signal(
            "knowledge.extracted",
            facts=facts,
            source=source,
        )

    # ── 状态接口 ──

    def status(self) -> dict:
        """返回总线完整状态."""
        return {
            "status": self._status,
            "total_ticks": self._total_ticks,
            "module_count": len(self._modules),
            "modules": self.list_modules(),
            "active_signals": list(self._signals.keys()),
        }

    @property
    def is_running(self) -> bool:
        return self._status == "running"
