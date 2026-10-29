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
