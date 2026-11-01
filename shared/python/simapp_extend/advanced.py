"""DEV-16 自动化 / 多目标 / 长期成本：明确不支持，不宣称相对基线的收益。"""

from __future__ import annotations

from typing import Any, Dict, Optional

EXTEND_VERSION = "m5-extend-0.1"
BASELINE_PLANNER = "m2-plan-baseline-0.1"

ADVANCED_CAPABILITIES = (
    "nsga2",
    "multi_objective",
    "lifecycle_cost",
    "expansion_scale",
    "operability_scale",
    "calibrated_automation",
)

_M5_GOALS = (
    ("lifecycle_cost", "长期成本模型未实现，评价期与费用即便填写也不计算 horizon_cost。"),
    ("easy_automation", "自动化设备未经校准与集成证据，不能作为「省心智能化」目标。"),
    ("expandable", "扩容情景与改造量表未确认，不能比较改造量。"),
)


def _failure(code: str, message: str, *, action: str, correction: str) -> Dict[str, Any]:
    return {
        "failure": {"code": code, "message": message},
        "correction": {"action": action, "message": correction},
    }


def _base(capability: str) -> Dict[str, Any]:
    return {
        "capability": capability,
        "implemented": False,
        "status": "unsupported",
        "engineVersion": EXTEND_VERSION,
        "baselinePlanner": BASELINE_PLANNER,
        "claimsBetterThanBaseline": False,
        "benefitProven": False,
        "claimsSavings": False,
        "claimsThroughput": False,
        "searchRan": False,
        "candidates": [],
        "score": None,
        "horizonCost": None,
        "npv": None,
        "payback": None,
        "savingsRate": None,
        "supportedInConclusion": False,
    }


def assess_advanced(
    *,
    capability: str,
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """高级优化/长期成本入口。忽略调用方自带的分数、收益和候选。"""
    raw = dict(inputs or {})
    raw.pop("score", None)
    raw.pop("horizonCost", None)
    raw.pop("npv", None)
    raw.pop("candidates", None)
    raw.pop("claimedImprovementPct", None)
    raw.pop("savingsRate", None)

    result = _base(capability)
    if capability not in ADVANCED_CAPABILITIES:
        result["status"] = "failed"
        result.update(
            _failure(
                "UNKNOWN_ADVANCED_CAPABILITY",
                f"不支持的高级能力：{capability}",
                action="use_baseline",
                correction="容量/初投请走现有规划与 M4 成本；不要把未登记能力当成优化结果。",
            )
        )
        return result

    if capability == "nsga2":
        result.update(
            _failure(
                "NSGA2_NOT_ADOPTED",
                "NSGA-II 只作为后续评估项。本切片不跑种群搜索，也不宣称优于模板枚举基线。",
                action="use_baseline_planner",
                correction=f"继续使用基线规划器 {BASELINE_PLANNER}（/planning-jobs）。没有可证实收益。",
            )
        )
        return result

    if capability == "multi_objective":
        requested = raw.get("goals") if isinstance(raw.get("goals"), list) else []
        disabled = [{"goal": goal, "reason": reason} for goal, reason in _M5_GOALS]
        known_baseline = {"capacity", "efficiency", "investment", "balanced"}
        extra = [g for g in requested if g not in known_baseline and g not in {d["goal"] for d in disabled}]
        for goal in extra:
            disabled.append({"goal": str(goal), "reason": "未建模目标，不能搜索也不能打分。"})
        result["disabledGoals"] = disabled
        result["acceptedGoals"] = []
        result.update(
            _failure(
                "MULTI_OBJECTIVE_UNSUPPORTED",
                "多目标高级搜索未实现。本入口不生成候选，也不把 M5 目标折成权重。",
                action="use_planning_jobs",
                correction="首期目标仍用 /planning-jobs 的模板枚举。lifecycle / easy_automation / expandable 保持禁用。",
            )
        )
        return result

    if capability == "lifecycle_cost":
        horizon = raw.get("horizonYears")
        fee_complete = raw.get("feeComplete") is True
        discount_requested = raw.get("discountRequested") is True
        rate = raw.get("discountRate")
        if not isinstance(horizon, (int, float)) or float(horizon) <= 0 or not fee_complete:
            code = "HORIZON_INCOMPLETE"
            message = "评价期或费用边界不完整。不计算长期成本，也不用已知小计冒充 horizon_cost。"
            action = "complete_horizon_fees"
            correction = "补齐评价年限、运营费用范围和口径后再评估。在模型实现前结果仍将是不支持。"
        elif discount_requested and not isinstance(rate, (int, float)):
            code = "DISCOUNT_RATE_MISSING"
            message = "要求折现但没有贴现率。不把未折现合计叫作 NPV。"
            action = "provide_discount_rate_or_skip"
            correction = "给出经确认的贴现率，或明确不做折现。当前两种都不产生数字。"
        else:
            code = "LIFECYCLE_NOT_IMPLEMENTED"
            message = "评价期数据看起来齐全，但长期成本 / 折现现金流模型未实现，不返回 horizon_cost。"
            action = "use_m4_capex"
            correction = "初投仍用 M4 capex（且缺价不排最低成本）。停工损失与回本期保持待评估。"
        result.update(_failure(code, message, action=action, correction=correction))
        return result

    if capability == "expansion_scale":
        has_scenario = bool(raw.get("growthScenarioId")) and bool(raw.get("scaleVersion"))
        if not has_scenario:
            code = "EXPANSION_SCALE_UNCONFIRMED"
            message = "没有已确认的增长情景与量表版本。扩容轴分数为空，不补 0。"
            correction = "确认增长目标、预留和改造规则并版本化量表后再启用该轴。"
        else:
            code = "EXPANSION_SCALE_NOT_IMPLEMENTED"
            message = "已提供情景标识，但扩容改动量模型未实现。分数仍为空。"
            correction = "不要把情景 id 当成改造费用。该轴保持不可用。"
        result["axisId"] = "expansion"
        result["axisStatus"] = "unavailable"
        result.update(
            _failure(code, message, action="keep_axis_unavailable", correction=correction)
        )
        return result

    if capability == "operability_scale":
        evidence = raw.get("evidenceRefs")
        has_evidence = isinstance(evidence, list) and len(evidence) > 0 and bool(raw.get("scaleVersion"))
        if not has_evidence:
            code = "OPERABILITY_EVIDENCE_MISSING"
            message = "没有培训、人工干预、维护覆盖或故障恢复的可核查量表。运维轴不打分。"
            correction = "faultInject / skillTags 占位不算运维证据。补齐量表前不要把该轴画进雷达。"
        else:
            code = "OPERABILITY_SCALE_NOT_IMPLEMENTED"
            message = "已给出证据引用，但运维量表未实现。分数仍为空，不补 0。"
            correction = "证据引用只被记录为输入，不换算成分数。"
        result["axisId"] = "operability"
        result["axisStatus"] = "unavailable"
        result.update(
            _failure(code, message, action="keep_axis_unavailable", correction=correction)
        )
        return result

    # calibrated_automation
    evidence = raw.get("calibrationEvidenceRefs")
    has_evidence = isinstance(evidence, list) and len(evidence) > 0
    if not has_evidence or raw.get("calibrated") is not True:
        code = "AUTOMATION_UNCALIBRATED"
        message = "输送 / AGV / ASRS 等自动化未经校准证据，不能进入接量或达标结论。"
        correction = "在设备适用性、节拍和集成证据确认前，只保留人工主路径。系统不会自动换成自动化设备。"
    else:
        code = "AUTOMATION_MODEL_NOT_IMPLEMENTED"
        message = "已标记校准并给出证据引用，但自动化作业模型未实现，仍不能计入吞吐。"
        correction = "证据不会被换成节拍或利用率。推演结论继续只覆盖已建模的人工设备。"
    result.update(
        _failure(code, message, action="stay_on_manual_model", correction=correction)
    )
    return result
