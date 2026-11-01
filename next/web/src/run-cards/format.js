/** Display rules. Null is not rendered as 0 seconds or 100%. */

export function formatNumber(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  const rounded = Math.round(value * 1000) / 1000;
  return String(rounded);
}

export function formatWait(mean) {
  if (mean === null || mean === undefined) return "无完成任务";
  return formatNumber(mean);
}

export function formatP95(value) {
  if (value === null || value === undefined) return "无完成任务";
  return formatNumber(value);
}

export function formatRate(rate) {
  if (rate === null || rate === undefined) return "不适用";
  return `${formatNumber(rate * 100)}%`;
}

export function formatThroughput(value) {
  if (value === null || value === undefined) return "—";
  return formatNumber(value);
}

export function staleMessage({ layoutChanged, demandChanged, scenarioChanged }) {
  const reasons = [];
  if (layoutChanged) reasons.push("布局已改变");
  if (demandChanged) reasons.push("需求已改变");
  else if (scenarioChanged) reasons.push("工况已改变");
  if (!reasons.length) return null;
  return `这条结果已过期：${reasons.join("；")}。`;
}

export function acceptRun(payload) {
  if (!payload || payload.kpiFromUiDemo !== false) {
    return { ok: false, error: "结果被拒绝：响应标明来自界面演示数。" };
  }
  return { ok: true, run: payload };
}

/** Transcribe the four cards already on this run. No prices, no extra KPIs. */
export function runReport(run) {
  if (!run || run.kpiFromUiDemo !== false) return "";
  const cards = run.cards || {};
  const throughput = cards.throughput || {};
  const wait = cards.wait || {};
  const util = cards.utilization || {};
  const bottle = cards.bottleneck || {};
  const types = (util.byResourceType || []).map((row) => `${row.resourceType} ${formatRate(row.utilization ?? null)}`);
  const ids = (util.byResource || []).map((row) => `${row.resourceId} ${formatRate(row.utilization ?? null)}`);
  const top = (bottle.topN || [])[0];
  const manifest = run.runManifest || {};
  const lines = [
    "仿真报告",
    `布局修订 ${run.layoutRevision || "未签发"}`,
    `引擎 ${manifest.engineVersion || "未签发"}`,
    `托盘吞吐 ${formatThroughput(throughput.value ?? null)} 托当量/时`,
    `任务等待 ${formatWait(wait.meanSec ?? null)} 秒`,
    `等待 P95 ${formatP95(wait.p95Sec ?? null)} 秒`,
    `资源利用率 ${types.join("，") || "无"}`,
    `资源 ${ids.join("，") || "无"}`,
    `主要瓶颈 ${top ? top.entityId : "无等待样本"}`,
    top ? `瓶颈等待 ${formatWait(top.waitSec ?? null)} 秒` : "瓶颈等待 无等待样本",
    "本报告只转写这一次运行的四卡，不含价格。",
  ];
  return lines.join("\n");
}

/** count × a price the operator typed. Blank and negative prices do not become zero. */
export function unitAmount(count, unitPrice) {
  if (typeof count !== "number" || !Number.isFinite(count)) return { ok: false, text: "台数还没有" };
  if (unitPrice === null || unitPrice === undefined || unitPrice === "") return { ok: false, text: "叉车单价未填写" };
  const price = typeof unitPrice === "number" ? unitPrice : Number(unitPrice);
  if (!Number.isFinite(price)) return { ok: false, text: "叉车单价未填写" };
  if (price < 0) return { ok: false, text: "单价不能为负" };
  const amount = count * price;
  return {
    ok: true,
    amount,
    text: `${formatNumber(count)} 台 × ${formatNumber(price)} = ${formatNumber(amount)}。单价来自这次填写。`,
  };
}

function cardNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function signed(value) {
  const text = formatNumber(value);
  return value > 0 ? `+${text}` : text;
}

function priceOrNull(prices, key) {
  if (!prices || prices[key] === null || prices[key] === undefined || prices[key] === "") return null;
  const price = typeof prices[key] === "number" ? prices[key] : Number(prices[key]);
  return Number.isFinite(price) ? price : null;
}

function countOf(rows, type) {
  const row = rows.find((item) => item.resourceType === type);
  return row ? cardNumber(row.resourceCount) : null;
}

/** Four cards copied off one run. Prices are the numbers typed at this moment. Missing waits stay null. */
export function pinCards(run, prices) {
  if (!run || run.kpiFromUiDemo !== false || !run.cards) return null;
  const cards = run.cards;
  const wait = cards.wait || {};
  const throughput = cards.throughput || {};
  const rows = (cards.utilization || {}).byResourceType || [];
  const top = ((cards.bottleneck || {}).topN || [])[0] || null;
  return {
    layoutRevision: String(run.layoutRevision || ""),
    throughput: cardNumber(throughput.value),
    waitMeanSec: cardNumber(wait.meanSec),
    waitP95Sec: cardNumber(wait.p95Sec),
    forkliftCount: countOf(rows, "forklift"),
    pickerCount: countOf(rows, "picker"),
    agvCount: countOf(rows, "agv"),
    utilization: rows.map((row) => ({
      resourceType: String(row.resourceType || ""),
      utilization: cardNumber(row.utilization),
    })),
    bottleneckId: top && top.entityId ? String(top.entityId) : "",
    bottleneckWaitSec: top ? cardNumber(top.waitSec) : null,
    prices: {
      forklift: priceOrNull(prices, "forklift"),
      picker: priceOrNull(prices, "picker"),
      agv: priceOrNull(prices, "agv"),
    },
  };
}

function throughputText(value) {
  if (value === null || value === undefined) return "没有吞吐数字";
  return formatNumber(value);
}

function utilMap(pin) {
  const map = {};
  for (const row of pin.utilization || []) map[row.resourceType] = cardNumber(row.utilization);
  return map;
}

/** Difference of two pinned runs. A missing sample is not written as zero. */
export function cardDeltaText(pinned, current) {
  if (!pinned || !current) return "先记下一次运行的四卡。";
  const same = pinned.layoutRevision !== "" && pinned.layoutRevision === current.layoutRevision;
  const throughputDelta = cardNumber(current.throughput) === null || cardNumber(pinned.throughput) === null
    ? null
    : current.throughput - pinned.throughput;
  const waitDelta = cardNumber(current.waitMeanSec) === null || cardNumber(pinned.waitMeanSec) === null
    ? null
    : current.waitMeanSec - pinned.waitMeanSec;
  const lines = [
    same ? "两次是同一布局修订。" : "两次布局修订不同。",
    `上次 ${pinned.layoutRevision || "未签发"} 吞吐 ${throughputText(pinned.throughput)} 等待 ${formatWait(pinned.waitMeanSec)}`,
    `这次 ${current.layoutRevision || "未签发"} 吞吐 ${throughputText(current.throughput)} 等待 ${formatWait(current.waitMeanSec)}`,
    `吞吐相差 ${throughputDelta === null ? "没有吞吐数字" : signed(throughputDelta)}`,
    `等待相差 ${waitDelta === null ? "无完成任务" : signed(waitDelta)} 秒`,
  ];
  if (throughputDelta === 0 && waitDelta !== null && waitDelta !== 0) {
    lines.push("吞吐相同，等待不同，这不是同样的效率。");
  }
  const seen = new Set([
    ...Object.keys(utilMap(pinned)),
    ...Object.keys(utilMap(current)),
  ]);
  const leftUtil = utilMap(pinned);
  const rightUtil = utilMap(current);
  for (const type of seen) {
    if (!type) continue;
    const before = leftUtil[type];
    const after = rightUtil[type];
    if (before === null || before === undefined || after === null || after === undefined) {
      lines.push(`利用率 ${type} 有一侧没有，不把缺的写成 0。`);
      continue;
    }
    lines.push(`利用率 ${type} 相差 ${signed((after - before) * 100)} 个百分点`);
  }
  const beforeBottle = pinned.bottleneckId || "";
  const afterBottle = current.bottleneckId || "";
  if (!beforeBottle && !afterBottle) lines.push("主要瓶颈 无等待样本");
  else if (beforeBottle === afterBottle) lines.push(`主要瓶颈 两次都是 ${beforeBottle}`);
  else lines.push(`主要瓶颈 上次 ${beforeBottle || "无等待样本"}，这次 ${afterBottle || "无等待样本"}。对象不同，不相减。`);
  const crews = [
    ["forkliftCount", "叉车"],
    ["pickerCount", "拣货人"],
    ["agvCount", "AGV"],
  ];
  for (const [key, label] of crews) {
    const before = cardNumber(pinned[key]);
    const after = cardNumber(current[key]);
    if (before === null || after === null || before === after) continue;
    lines.push(`${label}台数不同，吞吐和等待的差不能全部算到布局上。`);
  }
  return lines.join("\n");
}

const SHEET_ROWS = [
  ["forklift", "forkliftCount", "叉车", "台"],
  ["picker", "pickerCount", "拣货人", "人"],
  ["agv", "agvCount", "AGV", "台"],
];

/** Sum only the resources that actually ran. A blank price blocks the total. */
export function sheetAmount(pin) {
  if (!pin) return { ok: false, total: null, text: "" };
  const lines = [];
  let total = 0;
  let missing = false;
  let any = false;
  for (const [key, countKey, label, unit] of SHEET_ROWS) {
    const count = cardNumber(pin[countKey]);
    if (count === null || count <= 0) continue;
    any = true;
    const price = pin.prices ? pin.prices[key] : null;
    if (price === null || price === undefined) {
      missing = true;
      lines.push(`${label} ${formatNumber(count)} ${unit}，单价未填写`);
      continue;
    }
    if (price < 0) {
      missing = true;
      lines.push(`${label}单价不能为负`);
      continue;
    }
    const amount = count * price;
    total += amount;
    lines.push(`${label} ${formatNumber(count)} ${unit} × ${formatNumber(price)} = ${formatNumber(amount)}`);
  }
  if (!any) return { ok: false, total: null, text: "" };
  if (missing) {
    return { ok: false, total: null, text: `${lines.join("\n")}\n有单价没填，不算合计，也不比哪一次更省。` };
  }
  return { ok: true, total, text: `${lines.join("\n")}\n合计 ${formatNumber(total)}。单价来自这次填写。` };
}

/** Compare two frozen sheets. An incomplete price is not treated as zero and is not ranked. */
export function amountCompareText(pinned, current) {
  const left = sheetAmount(pinned);
  const right = sheetAmount(current);
  if (!left.text || !right.text) return "";
  if (!left.ok || !right.ok) return "有单价没填，不比哪一次更省。";
  const same = left.total === right.total;
  const verdict = same ? "两次手填合计相同。" : right.total > left.total ? "这次手填合计更高。" : "上次手填合计更高。";
  return `上次合计 ${formatNumber(left.total)}，这次合计 ${formatNumber(right.total)}。${verdict}只比较这两次都填全的金额。`;
}
