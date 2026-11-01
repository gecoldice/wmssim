"""端到端交付报告：数值与不可变版本/跑次一致。"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_delivery_report(
    *,
    project: Dict[str, Any],
    variant: Dict[str, Any],
    layout_ref: Dict[str, str],
    run: Optional[Dict[str, Any]] = None,
    cost_estimate: Optional[Dict[str, Any]] = None,
    comparison: Optional[Dict[str, Any]] = None,
    support_scope: Optional[Dict[str, Any]] = None,
    report_id: Optional[str] = None,
) -> Dict[str, Any]:
    """生成绑定历史 revision/run 的报告快照 + HTML。

    一致性门禁：
    - run.layoutRevision == layout_ref.revision（若有 run）
    - cost_estimate.layoutRef 与 layout_ref 一致（若有成本）
    - 禁止用「当前草稿」替换指定跑次
    """
    inconsistencies: List[Dict[str, str]] = []

    run_layout_rev = None
    if run:
        run_layout_rev = (
            (run.get("trajectory") or {}).get("layoutRevision")
            or (run.get("replayBinding") or {}).get("layoutRevision")
            or (run.get("layoutSnapshotBound") or {}).get("layoutRevision")
        )
        if run_layout_rev and run_layout_rev != layout_ref.get("revision"):
            inconsistencies.append(
                {
                    "code": "LAYOUT_REVISION_MISMATCH",
                    "message": (
                        f"报告 layoutRevision={layout_ref.get('revision')} "
                        f"与 run 绑定 {run_layout_rev} 不一致"
                    ),
                }
            )

    if cost_estimate:
        cref = cost_estimate.get("layoutRef") or {}
        if cref.get("id") and cref.get("id") != layout_ref.get("id"):
            inconsistencies.append(
                {
                    "code": "LAYOUT_ID_MISMATCH",
                    "message": "成本估算 layoutId 与报告引用不一致",
                }
            )
        if cref.get("revision") and cref.get("revision") != layout_ref.get("revision"):
            inconsistencies.append(
                {
                    "code": "LAYOUT_REVISION_MISMATCH",
                    "message": "成本估算 layoutRevision 与报告引用不一致",
                }
            )

    consistent = len(inconsistencies) == 0
    rid = report_id or f"rpt-{uuid4().hex[:10]}"

    kpi_cards = ((run or {}).get("kpi") or {}).get("cards") if run else None
    support = support_scope or {
        "manualPath": True,
        "optionalPlanning": True,
        "des": True,
        "costCompare": True,
        "deferred": [
            "lifecycle/expansion/operability 雷达轴（M5）",
            "真 CSV/Excel BOM 导入",
            "折现现金流",
            "faultInject/skillTags 生效",
        ],
    }

    payload = {
        "contractVersion": "0.3",
        "id": rid,
        "format": "html",
        "projectRef": {"id": project.get("id"), "name": project.get("name")},
        "variantRef": {"id": variant.get("id"), "revision": variant.get("revision")},
        "layoutRef": dict(layout_ref),
        "runRef": {"runId": run.get("runId")} if run else None,
        "costEstimateRef": {"id": cost_estimate.get("id")} if cost_estimate else None,
        "comparisonRef": (
            {"id": comparison.get("id"), "revision": comparison.get("revision")}
            if comparison
            else None
        ),
        "versions": {
            "contractVersion": "0.3",
            "engineVersion": (run or {}).get("engineVersion"),
            "costEngineVersion": (cost_estimate or {}).get("costEngineVersion"),
            "compareEngineVersion": (comparison or {}).get("compareEngineVersion"),
            "metricDefinitionVersion": ((run or {}).get("runManifest") or {}).get(
                "metricDefinitionVersion"
            ),
        },
        "kpiCards": kpi_cards,
        "costTotals": (cost_estimate or {}).get("totals"),
        "costStatus": (cost_estimate or {}).get("status"),
        "supportScope": support,
        "versionConsistent": consistent,
        "inconsistencies": inconsistencies,
        "computedAt": _now(),
        "kpiFromUiDemo": False,
    }

    html = _render_html(payload, run=run, cost_estimate=cost_estimate, comparison=comparison)
    payload["html"] = html
    return payload


def _render_html(
    payload: Dict[str, Any],
    *,
    run: Optional[Dict[str, Any]],
    cost_estimate: Optional[Dict[str, Any]],
    comparison: Optional[Dict[str, Any]],
) -> str:
    def cell(v: Any) -> str:
        return escape("—" if v is None else str(v))

    cards = payload.get("kpiCards") or {}
    thr = (cards.get("throughput") or {}).get("outboundPalletEq")
    wait = (cards.get("wait") or {}).get("meanSec")
    lines = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'/>",
        f"<title>simapp 交付报告 {escape(payload['id'])}</title>",
        "<style>body{font-family:system-ui,sans-serif;max-width:880px;margin:2rem auto;padding:0 1rem}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}"
        ".warn{color:#a40}.ok{color:#060}</style></head><body>",
        f"<h1>simapp 交付报告</h1>",
        f"<p>报告 ID：<code>{escape(payload['id'])}</code> · 生成于 {escape(payload['computedAt'])}</p>",
        (
            f"<p class='ok'>版本一致：与指定 layoutRevision / run 对齐</p>"
            if payload["versionConsistent"]
            else f"<p class='warn'>版本不一致：{escape(str(payload['inconsistencies']))}</p>"
        ),
        "<h2>绑定引用</h2><table>",
        f"<tr><th>项目</th><td>{cell((payload.get('projectRef') or {}).get('name'))} "
        f"({cell((payload.get('projectRef') or {}).get('id'))})</td></tr>",
        f"<tr><th>方案</th><td>{cell((payload.get('variantRef') or {}).get('id'))}@"
        f"{cell((payload.get('variantRef') or {}).get('revision'))}</td></tr>",
        f"<tr><th>布局修订</th><td>{cell((payload.get('layoutRef') or {}).get('id'))}@"
        f"{cell((payload.get('layoutRef') or {}).get('revision'))}</td></tr>",
        f"<tr><th>跑次</th><td>{cell((payload.get('runRef') or {}).get('runId'))}</td></tr>",
        f"<tr><th>成本估算</th><td>{cell((payload.get('costEstimateRef') or {}).get('id'))} "
        f"status={cell(payload.get('costStatus'))}</td></tr>",
        f"<tr><th>比较集合</th><td>{cell((payload.get('comparisonRef') or {}).get('id'))}</td></tr>",
        "</table>",
        "<h2>推演四卡（事件派生）</h2><table>",
        f"<tr><th>吞吐 outboundPalletEq</th><td>{cell(thr)}</td></tr>",
        f"<tr><th>等待均值 sec</th><td>{cell(wait)}</td></tr>",
        "</table>",
        "<h2>成本</h2><table>",
        f"<tr><th>status</th><td>{cell(payload.get('costStatus'))}</td></tr>",
        f"<tr><th>knownSubtotal</th><td>{cell(((payload.get('costTotals') or {}).get('knownSubtotal')))}</td></tr>",
        f"<tr><th>capex/total</th><td>{cell(((payload.get('costTotals') or {}).get('capex')))} / "
        f"{cell(((payload.get('costTotals') or {}).get('total')))}</td></tr>",
        "</table>",
        "<p>缺价时 total 为 null，不可宣称最低总成本。</p>",
        "<h2>支持范围</h2><ul>",
    ]
    deferred = (payload.get("supportScope") or {}).get("deferred") or []
    for d in deferred:
        lines.append(f"<li>延后：{escape(str(d))}</li>")
    lines.append("</ul>")
    if comparison:
        lines.append(
            f"<p>比较 mode={escape(str(comparison.get('mode')))} · "
            f"radarEnabled={escape(str((comparison.get('radar') or {}).get('radarEnabled')))}</p>"
        )
    if cost_estimate and cost_estimate.get("missingItems"):
        lines.append("<h2>缺价项</h2><ul>")
        for m in cost_estimate["missingItems"]:
            lines.append(
                f"<li>{escape(str(m.get('skuKey')))} × {escape(str(m.get('qty')))} "
                f"({escape(str(m.get('reason')))})</li>"
            )
        lines.append("</ul>")
    if run:
        lines.append(
            f"<p>engineVersion={escape(str(run.get('engineVersion')))} · "
            f"kpiFromUiDemo={escape(str(run.get('kpiFromUiDemo')))}</p>"
        )
    lines.append("</body></html>")
    return "\n".join(lines)
