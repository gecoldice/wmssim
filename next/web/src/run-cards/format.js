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

/** Four numbers copied off one run. Missing waits stay null. */
export function pinCards(run) {
  if (!run || run.kpiFromUiDemo !== false || !run.cards) return null;
  const cards = run.cards;
  const wait = cards.wait || {};
  const throughput = cards.throughput || {};
  const fork = ((cards.utilization || {}).byResourceType || []).find((row) => row.resourceType === "forklift");
  const top = ((cards.bottleneck || {}).topN || [])[0] || null;
  return {
    layoutRevision: String(run.layoutRevision || ""),
    throughput: cardNumber(throughput.value),
    waitMeanSec: cardNumber(wait.meanSec),
    waitP95Sec: cardNumber(wait.p95Sec),
    forkliftCount: fork ? cardNumber(fork.resourceCount) : null,
    bottleneckId: top && top.entityId ? String(top.entityId) : "",
  };
}

function throughputText(value) {
  if (value === null || value === undefined) return "没有吞吐数字";
  return formatNumber(value);
}

/** Difference of two pinned runs. Null samples are not treated as zero. */
export function cardDeltaText(pinned, current) {
  if (!pinned || !current) return "先记下一次运行的四卡。";
  const same = pinned.layoutRevision !== "" && pinned.layoutRevision === current.layoutRevision;
  const throughputDelta = cardNumber(current.throughput) === null || cardNumber(pinned.throughput) === null
    ? null
    : current.throughput - pinned.throughput;
  const waitDelta = cardNumber(current.waitMeanSec) === null || cardNumber(pinned.waitMeanSec) === null
    ? null
    : current.waitMeanSec - pinned.waitMeanSec;
  return [
    same ? "两次是同一布局修订。" : "两次布局修订不同。",
    `上次 ${pinned.layoutRevision || "未签发"} 吞吐 ${throughputText(pinned.throughput)} 等待 ${formatWait(pinned.waitMeanSec)}`,
    `这次 ${current.layoutRevision || "未签发"} 吞吐 ${throughputText(current.throughput)} 等待 ${formatWait(current.waitMeanSec)}`,
    `吞吐相差 ${throughputDelta === null ? "没有吞吐数字" : signed(throughputDelta)}`,
    `等待相差 ${waitDelta === null ? "无完成任务" : signed(waitDelta)} 秒`,
  ].join("\n");
}
