"""记忆异常检测 —— 主动标记高情感强度和异常模式.

模式 G 的补充：Memory 不只被动存储，还能主动扫描已编码的记忆，
标记那些值得特别关注的"特征时刻"。
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("echo.memory.anomaly")


@dataclass
class AnomalyScan:
    """一次异常扫描的结果."""
    scanned: int = 0          # 扫描的记忆数
    flagged: int = 0          # 标记为异常的记忆数
    high_emotion: int = 0     # 高情感强度
    pattern_shift: int = 0    # 情绪突变（连续记忆间 valence 跳跃）
    rare_topic: int = 0        # 罕见话题
    details: list[dict] = field(default_factory=list)


def detect_anomalies(memory_store, recent_count: int = 50,
                     emotion_threshold: float = 0.6) -> AnomalyScan:
    """扫描最近的记忆，标记异常.

    检测三种异常类型：
    1. 高情感强度（|valence| > threshold 或 arousal > threshold）
    2. 情绪突变（连续两条记忆之间 valence 跳跃 > 0.5）
    3. 罕见话题（标签组合在历史中 < 3 次出现）

    Args:
        memory_store: MemoryStore 实例
        recent_count: 扫描最近的 N 条记忆
        emotion_threshold: 情感强度阈值

    Returns:
        AnomalyScan: 扫描结果统计
    """
    recent = memory_store.list_active(limit=recent_count)
    if len(recent) < 2:
        return AnomalyScan(scanned=len(recent))

    scan = AnomalyScan(scanned=len(recent))
    tagged_ids = []

    # 检测 1: 高情感强度
    for mem in recent:
        intensity = abs(mem.emotional_valence) + mem.emotional_arousal
        if intensity > emotion_threshold:
            scan.high_emotion += 1
            scan.details.append({
                "memory_id": mem.id,
                "type": "high_emotion",
                "intensity": round(intensity, 2),
                "preview": mem.content[:80],
                "valence": mem.emotional_valence,
                "arousal": mem.emotional_arousal,
            })
            tagged_ids.append(mem.id)

    # 检测 2: 情绪突变（按时间排序后检查连续 memory 间的情感跳跃）
    sorted_memories = sorted(recent, key=lambda m: m.created_at)
    for i in range(1, len(sorted_memories)):
        prev_v = sorted_memories[i-1].emotional_valence
        curr_v = sorted_memories[i].emotional_valence
        jump = abs(curr_v - prev_v)
        if jump > 0.5:
            scan.pattern_shift += 1
            mem_id = sorted_memories[i].id
            scan.details.append({
                "memory_id": mem_id,
                "type": "pattern_shift",
                "valence_jump": round(jump, 2),
                "from_valence": prev_v,
                "to_valence": curr_v,
                "preview": sorted_memories[i].content[:80],
            })
            if mem_id not in tagged_ids:
                tagged_ids.append(mem_id)

    # 检测 3: 罕见话题
    tag_freq = {}
    for mem in recent:
        for tag in (mem.tags or []):
            tag_freq[tag] = tag_freq.get(tag, 0) + 1

    for mem in recent:
        rare_tags = [t for t in (mem.tags or [])
                     if tag_freq.get(t, 0) < 3]
        if rare_tags:
            scan.rare_topic += 1
            scan.details.append({
                "memory_id": mem.id,
                "type": "rare_topic",
                "rare_tags": rare_tags,
                "preview": mem.content[:80],
            })
            if mem.id not in tagged_ids:
                tagged_ids.append(mem.id)

    # 为被标记的记忆添加 anomaly 标签
    if tagged_ids:
        _tag_anomalies(memory_store, tagged_ids)

    scan.flagged = len(scan.details)
    if scan.flagged > 0:
        logger.info(
            f"异常扫描: {scan.scanned} 条中标记了 {scan.flagged} 条异常 "
            f"(高情感:{scan.high_emotion} 突变:{scan.pattern_shift} "
            f"罕见:{scan.rare_topic})"
        )

    return scan


def _tag_anomalies(memory_store, memory_ids: list[str]) -> None:
    """为标记的记忆添加 'anomaly' 标签并提升权重."""
    try:
        conn = memory_store._conn
        placeholders = ",".join("?" * len(memory_ids))
        conn.execute(f"""
            UPDATE memories SET
                tags = CASE
                    WHEN tags IS NULL OR tags = '[]' THEN '["anomaly"]'
                    WHEN tags NOT LIKE '%anomaly%'
                        THEN json_insert(tags, '$[#]', 'anomaly')
                    ELSE tags
                END,
                base_weight = MIN(1.0, base_weight + 0.05),
                half_life_hours = MIN(672, half_life_hours * 1.5)
            WHERE id IN ({placeholders})
        """, memory_ids)
        conn.commit()
    except Exception as e:
        logger.warning(f"异常标记失败: {e}")


def summarize_anomalies(scan: AnomalyScan) -> str:
    """生成异常扫描的人类可读摘要."""
    if scan.flagged == 0:
        return f"扫描 {scan.scanned} 条记忆，未发现异常。"

    lines = [
        f"扫描 {scan.scanned} 条记忆，发现 {scan.flagged} 条异常：",
        f"  🔥 高情感强度: {scan.high_emotion} 条",
        f"  📈 情绪突变:    {scan.pattern_shift} 次",
        f"  🏷️ 罕见话题:    {scan.rare_topic} 个",
        "",
        "详情:",
    ]

    for d in scan.details[:10]:  # 最多 10 条
        e_type = {"high_emotion": "🔥", "pattern_shift": "📈", "rare_topic": "🏷️"}[d["type"]]
        lines.append(f"  {e_type} [{d['memory_id'][:8]}] {d['preview']}...")

    return "\n".join(lines)
