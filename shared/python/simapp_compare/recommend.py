"""比较集合内推荐：容量 / 初投；限定「本组已验证候选」。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from simapp_cost.rank import recommend_lowest_capex


def recommend_capacity(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """在硬约束通过且有容量值的候选中选更大者。"""
    if not (comparison.get("comparability") or {}).get("comparable", True):
        return {
            "goal": "capacity",
            "rankingUnavailable": True,
            "code": "INCOMPARABLE_RESULTS",
            "message": "比较口径不一致，不排序",
            "winner": None,
            "scopeNote": "在本组已评估候选中",
        }

    eligible = []
    excluded = []
    for e in comparison.get("entries") or []:
        if not e.get("hardGatePass", True):
            excluded.append({"entryId": e.get("entryId"), "reason": "hard_gate_fail"})
            continue
        cap = (e.get("metrics") or {}).get("effective_capacity")
        if cap is None:
            excluded.append({"entryId": e.get("entryId"), "reason": "missing_capacity"})
            continue
        eligible.append(e)

    if not eligible:
        return {
            "goal": "capacity",
            "rankingUnavailable": True,
            "code": "MISSING_METRIC",
            "message": "无可用容量候选",
            "winner": None,
            "excluded": excluded,
            "scopeNote": "在本组已评估候选中",
        }

    ranked = sorted(
        eligible,
        key=lambda e: (-float((e.get("metrics") or {}).get("effective_capacity")), e.get("entryId") or ""),
    )
    w = ranked[0]
    return {
        "goal": "capacity",
        "rankingUnavailable": False,
        "message": (
            f"在本组已验证候选中，有效容量较大者为 {w.get('label')} "
            f"({(w.get('metrics') or {}).get('effective_capacity')})"
        ),
        "winner": {
            "entryId": w.get("entryId"),
            "label": w.get("label"),
            "effectiveCapacity": (w.get("metrics") or {}).get("effective_capacity"),
            "variantRef": w.get("variantRef"),
        },
        "ranked": [
            {
                "entryId": e.get("entryId"),
                "effectiveCapacity": (e.get("metrics") or {}).get("effective_capacity"),
                "rank": i + 1,
            }
            for i, e in enumerate(ranked)
        ],
        "excluded": excluded,
        "scopeNote": "在本组已评估候选中",
    }


def recommend_from_comparison(
    comparison: Dict[str, Any],
    *,
    cost_estimates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """汇总容量 + 初投推荐；不以雷达面积作推荐。"""
    capacity = recommend_capacity(comparison)

    estimates: List[Dict[str, Any]] = list(cost_estimates or [])
    if not estimates:
        # 从 table/metrics 重建最小 estimate 视图供排序
        for e in comparison.get("entries") or []:
            m = e.get("metrics") or {}
            complete = m.get("costStatus") == "complete" and m.get("capex") is not None
            estimates.append(
                {
                    "id": (e.get("costEstimateRef") or {}).get("id") or e.get("entryId"),
                    "variantRef": e.get("variantRef"),
                    "status": "complete" if complete else "incomplete",
                    "eligibleForLowestCostRanking": complete and m.get("eligibleForLowestCostRanking", complete),
                    "totals": {
                        "capex": m.get("capex"),
                        "total": m.get("capex") if complete else None,
                        "currency": "CNY",
                    },
                    "missingItems": [] if complete else [{"reason": "incomplete_in_comparison"}],
                }
            )

    cost = recommend_lowest_capex(estimates)
    return {
        "capacity": capacity,
        "lowestCapex": cost,
        "notes": [
            "不以雷达面积作推荐",
            "未完成仿真的方案不能显示「效率最高」",
            "推荐语限定：在本组已验证候选中",
        ],
    }
