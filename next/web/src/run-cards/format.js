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
