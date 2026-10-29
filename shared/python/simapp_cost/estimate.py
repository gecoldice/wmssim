"""CostEstimate：缺价显式处理；不完整时无 knownSubtotal，禁止完整 total。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .bom import build_bom_lines

COST_ENGINE_VERSION = "m4-cost-0.1"


class CostError(Exception):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _price_lookup(price_book: Dict[str, Any], sku_key: str) -> Optional[Dict[str, Any]]:
    for row in price_book.get("items") or []:
        if row.get("skuKey") == sku_key:
            return row
    return None


def _fee_rate(cost_basis: Dict[str, Any], fee_kind: str) -> float:
    for fee in cost_basis.get("feeSchedule") or []:
        if fee.get("kind") == fee_kind:
            return float(fee.get("rate") or 0.0)
    return 0.0


def estimate_cost(
    *,
    layout: Dict[str, Any],
    price_book: Dict[str, Any],
    cost_basis: Dict[str, Any],
    variant_ref: Optional[Dict[str, str]] = None,
    operating: Optional[Dict[str, Any]] = None,
    estimate_id: Optional[str] = None,
) -> Dict[str, Any]:
    """从布局 BOM × PriceBook × CostBasis 生成 CostEstimate。

    规则（05 §4 / DEV-12）：
    - existing：新增采购费 = 0；可有 relocate 费
    - new：采购价 + 可选安装费（安装不与单价重复）
    - relocated：只计搬移费，不计新购
    - 缺价 / 币种不可合并 → missingItems；status=incomplete；totals 仅 knownSubtotal
    - 购置价已计入时不加折旧（本切片不生成折旧行）
    """
    currency = cost_basis.get("currency") or price_book.get("currency")
    if not currency:
        raise CostError("INPUT_UNCONFIRMED", "CostBasis/PriceBook 须声明 currency")

    pb_currency = price_book.get("currency")
    if pb_currency and pb_currency != currency:
        # 缺汇率不合并
        fx = cost_basis.get("fxRate")
        if not fx or fx.get("from") != pb_currency or fx.get("to") != currency:
            raise CostError(
                "PRICE_INCOMPLETE",
                "PriceBook 与 CostBasis 币种不同且缺少经确认汇率，不合并",
                details={"priceBookCurrency": pb_currency, "costBasisCurrency": currency},
            )

    bom = build_bom_lines(layout, operating=operating)
    items: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    known = 0.0
    install_rate = _fee_rate(cost_basis, "install")
    relocate_rate = _fee_rate(cost_basis, "relocate")
    # 防止「单价已含安装」再加安装
    include_install = bool(cost_basis.get("includeInstallFee", True))
    include_relocate = bool(cost_basis.get("includeRelocateFee", True))
    double_install_guard = bool(cost_basis.get("purchaseIncludesInstall", False))

    for bom_line in bom:
        sku = bom_line["skuKey"]
        qty = float(bom_line["qty"])
        disposition = bom_line["disposition"]
        category = bom_line["category"]
        price_row = _price_lookup(price_book, sku)

        # 运营资源：按年度运营现金计入 horizon；首期 capex 切片对 labor/resource 记 opex 行
        if disposition == "operating":
            if not price_row or price_row.get("status") == "missing" or price_row.get("unitPrice") is None:
                missing.append(
                    {
                        "skuKey": sku,
                        "qty": qty,
                        "reason": "missing_price",
                        "category": category,
                        "lineId": bom_line["lineId"],
                    }
                )
                continue
            unit = float(price_row["unitPrice"])
            amount = unit * qty
            known += amount
            items.append(
                {
                    "lineId": f"cost-{bom_line['lineId']}-opex",
                    "bomLineId": bom_line["lineId"],
                    "skuKey": sku,
                    "category": "opex",
                    "qty": qty,
                    "unitPrice": unit,
                    "amount": amount,
                    "currency": currency,
                    "feeKind": "operating",
                    "priceSource": {
                        "source": price_row.get("source"),
                        "asOf": price_row.get("asOf"),
                        "taxInclusive": price_row.get("taxInclusive"),
                    },
                }
            )
            continue

        # 设备：existing → 采购 0；relocated → 仅搬移
        purchase_needed = disposition == "new" and category == "equipment"
        relocate_needed = disposition == "relocated" or (
            disposition == "existing" and include_relocate and relocate_rate > 0
        )

        if purchase_needed:
            if not price_row or price_row.get("status") == "missing" or price_row.get("unitPrice") is None:
                missing.append(
                    {
                        "skuKey": sku,
                        "qty": qty,
                        "reason": "missing_price",
                        "category": "capex_purchase",
                        "lineId": bom_line["lineId"],
                        "instanceIds": (bom_line.get("sourceRefs") or {}).get("instanceIds"),
                    }
                )
            else:
                unit = float(price_row["unitPrice"])
                amount = unit * qty
                known += amount
                items.append(
                    {
                        "lineId": f"cost-{bom_line['lineId']}-purchase",
                        "bomLineId": bom_line["lineId"],
                        "skuKey": sku,
                        "category": "capex",
                        "qty": qty,
                        "unitPrice": unit,
                        "amount": amount,
                        "currency": currency,
                        "feeKind": "purchase",
                        "priceSource": {
                            "source": price_row.get("source"),
                            "asOf": price_row.get("asOf"),
                            "taxInclusive": price_row.get("taxInclusive"),
                        },
                    }
                )
                if include_install and install_rate > 0 and not double_install_guard:
                    inst = install_rate * qty
                    known += inst
                    items.append(
                        {
                            "lineId": f"cost-{bom_line['lineId']}-install",
                            "bomLineId": bom_line["lineId"],
                            "skuKey": sku,
                            "category": "capex",
                            "qty": qty,
                            "unitPrice": install_rate,
                            "amount": inst,
                            "currency": currency,
                            "feeKind": "install",
                            "note": "安装/集成；与采购单价分列，不重复",
                        }
                    )

        if relocate_needed and include_relocate:
            # 搬移费可有独立价目或 CostBasis 统一费率
            reloc_price = None
            reloc_row = _price_lookup(price_book, f"relocate:{sku}")
            if reloc_row and reloc_row.get("unitPrice") is not None and reloc_row.get("status") != "missing":
                reloc_price = float(reloc_row["unitPrice"])
            elif relocate_rate > 0:
                reloc_price = relocate_rate
            if reloc_price is None:
                missing.append(
                    {
                        "skuKey": sku,
                        "qty": qty,
                        "reason": "missing_relocate_price",
                        "category": "capex_relocate",
                        "lineId": bom_line["lineId"],
                    }
                )
            else:
                amount = reloc_price * qty
                known += amount
                items.append(
                    {
                        "lineId": f"cost-{bom_line['lineId']}-relocate",
                        "bomLineId": bom_line["lineId"],
                        "skuKey": sku,
                        "category": "capex",
                        "qty": qty,
                        "unitPrice": reloc_price,
                        "amount": amount,
                        "currency": currency,
                        "feeKind": "relocate",
                        "note": "既有设备搬移；不计新购",
                    }
                )

        if disposition == "existing" and not relocate_needed:
            # 显式零采购披露
            items.append(
                {
                    "lineId": f"cost-{bom_line['lineId']}-existing",
                    "bomLineId": bom_line["lineId"],
                    "skuKey": sku,
                    "category": "capex",
                    "qty": qty,
                    "unitPrice": 0.0,
                    "amount": 0.0,
                    "currency": currency,
                    "feeKind": "existing_zero_purchase",
                    "note": "复用既有设备：新增采购费为 0",
                }
            )

    complete = len(missing) == 0
    capex_known = sum(i["amount"] for i in items if i.get("category") == "capex")
    opex_known = sum(i["amount"] for i in items if i.get("category") == "opex")

    totals: Dict[str, Any] = {
        "currency": currency,
        "knownSubtotal": known,
        "capexKnownSubtotal": capex_known,
        "opexKnownSubtotal": opex_known,
        "complete": complete,
    }
    if complete:
        totals["capex"] = capex_known
        totals["horizonCostPartial"] = capex_known + opex_known
        totals["total"] = capex_known + opex_known
    else:
        # 明确不给完整 total，避免被当成最低成本依据
        totals["total"] = None
        totals["capex"] = None
        totals["note"] = "缺价；仅 knownSubtotal 可展示，不可宣称最低总成本"

    return {
        "contractVersion": "0.3",
        "id": estimate_id or f"cost-{uuid4().hex[:10]}",
        "costEngineVersion": COST_ENGINE_VERSION,
        "variantRef": variant_ref,
        "layoutRef": {"id": layout.get("id"), "revision": layout.get("revision")},
        "costBasisRef": {"id": cost_basis.get("id"), "revision": cost_basis.get("revision")},
        "priceBookRef": {"id": price_book.get("id"), "revision": price_book.get("revision")},
        "operatingRef": (
            {"id": operating.get("id"), "revision": operating.get("revision")}
            if operating
            else None
        ),
        "bom": bom,
        "items": items,
        "missingItems": missing,
        "status": "complete" if complete else "incomplete",
        "totals": totals,
        "eligibleForLowestCostRanking": complete,
        "computedAt": _now(),
        "kpiFromUiDemo": False,
    }
