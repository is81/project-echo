"""审查引擎 (Orbitofrontal Cortex).

在 LLM 生成草稿后、输出到用户前，对回复进行多维度审查。
支持两种审查模式：
- heuristic: 纯规则检查（零延迟、零成本，默认启用）
- llm: 使用 LLM 做深度审查（更全面但有延迟和成本）
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .dimensions import (
    ALL_DIMENSIONS,
    check_principle_alignment,
    check_honesty,
    check_conciseness,
    check_emptiness,
    check_emotional_consistency,
    check_self_consistency,
)

logger = logging.getLogger("echo.review")


@dataclass
class CritiqueResult:
    """审查结果."""
    verdict: str = "pass"    # "pass" | "revise" | "reject"
    concerns: list[str] = field(default_factory=list)
    confidence: float = 1.0  # 审查置信度 [0, 1]
    revised_text: str = ""   # 修正后文本（verdict="revise" 时）
    dimension_scores: dict = field(default_factory=dict)  # 各维度得分
    total_score: float = 1.0  # 加权总分


class CritiqueEngine:
    """审查引擎 —— 回响的"内心独白"回路.

    在语言模块生成草稿后，对回复进行多维度审计：
    1. 原则对齐（权重 1.5）
    2. 诚实度（权重 1.2）
    3. 情绪一致性
    4. 自指一致性（权重 1.3）
    5. 简洁度
    6. 空洞度

    使用方式:
        engine = CritiqueEngine(principles, emotional_state, anchors)
        result = engine.critique(draft, user_input)

        if result.verdict == "revise":
            # 需要修正
            revised = engine.revise(draft, result, llm_backend)
    """

    # 审查阈值
    PASS_THRESHOLD = 0.75      # 总分 >= 此值 → 通过
    REVISE_THRESHOLD = 0.40    # 总分 >= 此值 → 修正; 低于 → 拒绝
    CONCERN_SCORE_THRESHOLD = 0.6  # 单维度低于此分 → 记录 concern

    def __init__(self, principles: list[dict], emotional_state=None,
                 anchors=None, enabled: bool = True, mode: str = "heuristic",
                 log_path: str = ""):
        """初始化审查引擎.

        Args:
            principles: 基因原则列表 (from config/principles.yaml)
            emotional_state: EmotionalState 实例
            anchors: AnchorRegistry 实例
            enabled: 是否启用审查（可通过配置关闭）
            mode: "heuristic"（纯规则）或 "llm"（LLM 深度审查）
            log_path: 审查日志文件路径（空字符串 = 不持久化）
        """
        self._principles = principles
        self._emotional_state = emotional_state
        self._anchors = anchors
        self.enabled = enabled
        self.mode = mode
        self._log_path = log_path

        # 审查统计
        self.total_reviews = 0
        self.pass_count = 0
        self.revise_count = 0
        self.reject_count = 0

        # 审查历史（内存缓存，最近 100 条）
        self._history: list[dict] = []

    def critique(self, draft: str, user_input: str = "",
                 system_prompt: str = "") -> CritiqueResult:
        """对 LLM 草稿进行多维度审查.

        Args:
            draft: LLM 生成的原始回复草稿
            user_input: 用户原始输入（用于上下文感知的审查）
            system_prompt: 当前系统提示（用于理解回复的约束条件）

        Returns:
            CritiqueResult: 审查结果（pass/revise/reject + 具体问题）
        """
        if not self.enabled:
            return CritiqueResult(verdict="pass", confidence=0.0)

        self.total_reviews += 1

        # 运行所有审查维度
        dimension_results = self._run_all_dimensions(draft, user_input)

        # 计算加权总分
        total_weight = sum(d.weight for d in dimension_results)
        weighted_sum = sum(d.score * d.weight for d in dimension_results)
        total_score = weighted_sum / total_weight if total_weight > 0 else 1.0

        # 收集触发的 concerns
        concerns = [d.concern for d in dimension_results
                    if d.concern is not None and d.score < d.threshold]

        # 决定 verdict
        if total_score >= self.PASS_THRESHOLD:
            verdict = "pass"
            self.pass_count += 1
        elif total_score >= self.REVISE_THRESHOLD:
            verdict = "revise"
            self.revise_count += 1
        else:
            verdict = "reject"
            self.reject_count += 1

        # 记录审查日志
        self._log_critique(draft, verdict, total_score, concerns, dimension_results)

        return CritiqueResult(
            verdict=verdict,
            concerns=concerns,
            confidence=total_score,
            dimension_scores={
                d.name: {"score": round(d.score, 2), "threshold": d.threshold}
                for d in dimension_results
            },
            total_score=round(total_score, 3),
        )

    def _run_all_dimensions(self, draft: str, user_input: str) -> list:
        """运行所有审查维度，每个独立 try/except 保护."""
        from .dimensions import DimensionResult

        results = []

        # 维度 1: 原则对齐
        try:
            results.append(check_principle_alignment(draft, self._principles))
        except Exception as e:
            logger.warning(f"审查维度 '原则对齐' 异常: {e}")
            results.append(DimensionResult(name="原则对齐", score=1.0, threshold=0.6))

        # 维度 2: 诚实度
        try:
            results.append(check_honesty(draft, user_input))
        except Exception as e:
            logger.warning(f"审查维度 '诚实度' 异常: {e}")
            results.append(DimensionResult(name="诚实度", score=1.0, threshold=0.5))

        # 维度 3: 情绪一致性（如果有情绪状态）
        if self._emotional_state:
            try:
                results.append(
                    check_emotional_consistency(draft, self._emotional_state)
                )
            except Exception as e:
                logger.warning(f"审查维度 '情绪一致性' 异常: {e}")
                results.append(DimensionResult(name="情绪一致性", score=1.0, threshold=0.5))

        # 维度 4: 自指一致性（如果有已形成的锚点）
        if self._anchors:
            try:
                formed = self._anchors.list_formed()
                results.append(check_self_consistency(draft, formed))
            except Exception as e:
                logger.warning(f"审查维度 '自指一致性' 异常: {e}")
                results.append(DimensionResult(name="自指一致性", score=1.0, threshold=0.5))

        # 维度 5: 简洁度
        try:
            results.append(check_conciseness(draft))
        except Exception as e:
            logger.warning(f"审查维度 '简洁度' 异常: {e}")
            results.append(DimensionResult(name="简洁度", score=1.0, threshold=0.5))

        # 维度 6: 空洞度
        try:
            results.append(check_emptiness(draft))
        except Exception as e:
            logger.warning(f"审查维度 '空洞度' 异常: {e}")
            results.append(DimensionResult(name="空洞度", score=1.0, threshold=0.5))

        return results

    def revise(self, draft: str, result: CritiqueResult,
               llm_backend=None) -> str:
        """根据审查结果修正回复.

        Args:
            draft: 原始草稿
            result: 审查结果（包含 concerns）
            llm_backend: LLM 后端（用于 LLM 模式修正；如果 None 则用启发式修正）

        Returns:
            修正后的文本
        """
        if not result.concerns:
            return draft

        if llm_backend and self.mode == "llm":
            return self._llm_revise(draft, result, llm_backend)
        else:
            return self._heuristic_revise(draft, result)

    def _heuristic_revise(self, draft: str, result: CritiqueResult) -> str:
        """启发式修正: 基于规则直接修改文本."""
        revised = draft

        for concern in result.concerns:
            # 过长 → 截断到前 2-3 句
            if "过长" in concern or "太长" in concern:
                sentences = revised.replace("！", "。").replace("？", "。").split("。")
                # 保留前 3 句有意义的内容
                meaningful = [s.strip() for s in sentences if len(s.strip()) > 5]
                if len(meaningful) > 3:
                    revised = "。".join(meaningful[:3]) + "。"

            # 空洞套话 → 尝试删除
            if "空洞" in concern or "套话" in concern:
                empty_phrases = [
                    "你说得对。", "这是一个很好的问题。",
                    "这是一个复杂的问题。", "这个问题涉及到很多方面。",
                    "从多个角度来看，", "需要综合考虑。",
                ]
                for phrase in empty_phrases:
                    revised = revised.replace(phrase, "")

            # 绝对化表述 → 添加不确定性标记
            if "绝对" in concern or "确定" in concern:
                if "据我所知" not in revised and "也许" not in revised:
                    revised = "据我所知，" + revised

            # 冷漠表达 → 软化
            if "冷漠" in concern:
                revised = revised.replace("这不关我的事", "这个我不太了解")
                revised = revised.replace("我无所谓", "我都可以")

        return revised.strip() or draft

    def _llm_revise(self, draft: str, result: CritiqueResult,
                    llm_backend) -> str:
        """LLM 修正: 用 LLM 根据审查意见修改回复."""
        concerns_text = "\n".join(f"- {c}" for c in result.concerns)

        revision_prompt = (
            f"以下是你的原始回复草稿和审查意见。请根据审查意见修改回复。\n\n"
            f"原始回复:\n{draft}\n\n"
            f"审查意见:\n{concerns_text}\n\n"
            f"请直接输出修改后的回复（不要解释修改了什么）："
        )

        try:
            response = llm_backend.generate(
                prompt=revision_prompt,
                temperature=0.3,  # 低温，追求准确性
            )
            if response.text and len(response.text.strip()) > 5:
                return response.text.strip()
        except Exception as e:
            logger.warning(f"LLM 修正失败，回退到启发式修正: {e}")

        return self._heuristic_revise(draft, result)

    def _log_critique(self, draft: str, verdict: str, total_score: float,
                      concerns: list[str], dimension_results: list) -> None:
        """记录审查日志（用于事后分析和调优）."""
        if verdict == "pass" and total_score > 0.9:
            return  # 高分通过的不需要日志

        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "verdict": verdict,
                "total_score": round(total_score, 3),
                "concerns": concerns,
                "dimensions": {
                    d.name: {"score": round(d.score, 2), "concern": d.concern}
                    for d in dimension_results if d.concern
                },
                "draft_preview": draft[:150] + "..." if len(draft) > 150 else draft,
            }

            # 内存缓存（最近 100 条）
            self._history.append(log_entry)
            if len(self._history) > 100:
                self._history = self._history[-100:]

            # 文件持久化
            if self._log_path:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            logger.info(f"审查: {verdict} (score={total_score:.3f}) "
                       f"concerns={len(concerns)}")
        except Exception:
            pass  # 日志记录失败不影响审查

    def recent_logs(self, limit: int = 20) -> list[dict]:
        """返回最近的审查日志."""
        return self._history[-limit:]

    def stats(self) -> dict:
        """返回审查统计."""
        return {
            "total_reviews": self.total_reviews,
            "pass_count": self.pass_count,
            "revise_count": self.revise_count,
            "reject_count": self.reject_count,
            "pass_rate": (
                self.pass_count / self.total_reviews
                if self.total_reviews > 0 else 1.0
            ),
            "mode": self.mode,
            "enabled": self.enabled,
        }
