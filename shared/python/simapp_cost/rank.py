"""成本目标推荐：仅价格完整的候选参与最低成本排序。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def recommend_lowest_capex(
    estimates: List[Dict[str, Any]],
    *,
    require_service_ok: bool = False,
    service_flags: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """在价格完整的 CostEstimate 中选 capex 更低者。

    - incomplete / eligibleForLowestCostRanking=False → 排除，不得因此排「最低」
    - 无合格候选 → rankingUnavailable + PRICE_INCOMPLETE
    """
    service_flags = service_flags or {}
    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for est in estimates:
        eid = est.get("id")
        complete = (
            est.get("status") == "complete"
            and est.get("eligibleForLowestCostRanking") is True
            and (est.get("totals") or {}).get("total") is not None
            and (est.get("totals") or {}).get("capex") is not None
        )
        if require_service_ok and not service_flags.get(eid, False):
            excluded.append(
                {
                    "estimateId": eid,
                    "reason": "service_not_met",
                    "message": "未满足库存/服务门槛，不参与初投排序",
                }
            )
            continue
        if not complete:
            excluded.append(
                {
                    "estimateId": eid,
                    "reason": "PRICE_INCOMPLETE",
                    "missingItems": est.get("missingItems") or [],
                    "message": "缺价；不得参与最低成本排序",
                }
            )
            continue
        eligible.append(est)

    if not eligible:
        return {
            "goal": "lowest_capex",
            "rankingUnavailable": True,
            "code": "PRICE_INCOMPLETE",
            "message": "无价格完整候选；不可宣称最低成本",
            "winner": None,
            "ranked": [],
            "excluded": excluded,
            "scopeNote": "在本组已评估候选中",
        }

    ranked = sorted(
        eligible,
        key=lambda e: (
            float((e.get("totals") or {}).get("capex")),
            e.get("id") or "",
        ),
    )
    winner = ranked[0]
    return {
        "goal": "lowest_capex",
        "rankingUnavailable": False,
        "code": None,
        "message": (
            f"在本组已验证且价格完整的候选中，初投较低者为 {winner.get('id')} "
            f"(capex={(winner.get('totals') or {}).get('capex')})"
        ),
        "winner": {
            "estimateId": winner.get("id"),
            "variantRef": winner.get("variantRef"),
            "capex": (winner.get("totals") or {}).get("capex"),
            "currency": (winner.get("totals") or {}).get("currency"),
        },
        "ranked": [
            {
                "estimateId": e.get("id"),
                "capex": (e.get("totals") or {}).get("capex"),
                "rank": i + 1,
            }
            for i, e in enumerate(ranked)
        ],
        "excluded": excluded,
        "scopeNote": "在本组已评估候选中",
    }
