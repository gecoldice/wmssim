import { readAccepted, rememberAccepted, ACCEPTED_KEY } from "../src/persist/lastAccepted.js";
import { acceptRun, formatP95, formatRate, formatWait, staleMessage } from "../src/run-cards/format.js";

const memory = new Map();
const storage = {
  getItem: (key) => (memory.has(key) ? memory.get(key) : null),
  setItem: (key, value) => memory.set(key, value),
  removeItem: (key) => memory.delete(key),
};

memory.set("draft-only", JSON.stringify({ elements: [{ instanceId: "rack-9", x: 1 }] }));
if (readAccepted(storage) !== null) throw new Error("draft-only storage was treated as saved");

rememberAccepted(storage, { projectId: "pj_test", layoutId: "layout-main", revision: "should-not-stick" });
const saved = JSON.parse(storage.getItem(ACCEPTED_KEY));
if (saved.revision) throw new Error("accepted record stored a revision");
if (saved.projectId !== "pj_test" || saved.layoutId !== "layout-main") throw new Error("accepted pointer missing");
if (readAccepted(storage).layoutId !== "layout-main") throw new Error("readAccepted failed");

if (formatWait(null) !== "无完成任务") throw new Error("null wait");
if (formatP95(null) !== "无完成任务") throw new Error("null p95");
if (formatRate(null) !== "不适用") throw new Error("null rate");
if (String(formatWait(null)).includes("0")) throw new Error("null wait rendered a zero");
if (formatRate(null).includes("100")) throw new Error("null rate rendered 100%");

const layoutStale = staleMessage({ layoutChanged: true, demandChanged: false, scenarioChanged: false });
const demandStale = staleMessage({ layoutChanged: false, demandChanged: true, scenarioChanged: true });
if (layoutStale !== "这条结果已过期：布局已改变。") throw new Error(layoutStale);
if (demandStale !== "这条结果已过期：需求已改变。") throw new Error(demandStale);
if (staleMessage({ layoutChanged: false, demandChanged: false, scenarioChanged: false }) !== null) {
  throw new Error("fresh run marked stale");
}

const rejected = acceptRun({ kpiFromUiDemo: true, cards: { throughput: { value: 99 } } });
if (rejected.ok) throw new Error("demo payload accepted");
const kept = acceptRun({ kpiFromUiDemo: false, cards: { throughput: { value: 4 } } });
if (!kept.ok) throw new Error("real payload discarded");

console.log("DISPLAY layout-stale:", layoutStale);
console.log("DISPLAY demand-stale:", demandStale);
console.log("DISPLAY null-wait:", formatWait(null));
console.log("DISPLAY null-p95:", formatP95(null));
console.log("DISPLAY null-rate:", formatRate(null));
console.log("DISPLAY demo-rejected:", rejected.error);
console.log("DISPLAY accepted-keys:", Object.keys(saved).sort().join(","));
console.log("DISPLAY PASS");
