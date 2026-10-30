import { writeFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server.browser";
import { footprintCorners, assessPlacement, aabbHits, aabbOf, boxGap, columnBox, FIRE_LANE } from "../src/canvas/geom.ts";
import { catalog, LIBRARY_IDS, SLICE11_IDS, isLinearConveyor, isUnsimulated, unsimulatedMessage } from "../src/library/catalog.ts";
import { EQUIPS } from "../src/proxy/equip-index.ts";
import { buildFromEquip, buildPlaced, frameForZoom, interactionStyle, portsNearFootprint, PALETTE } from "../src/proxy/extrude.ts";
import { copy } from "../src/copy.ts";
import { RunCards } from "../src/run-cards/RunCards.tsx";
import { actorsAt, segmentBounds } from "../src/run-cards/playback.ts";
import { applyNormFix, auditNorms, normNote, normSummary } from "../src/prepare/norms.ts";
import { InspectorPanel } from "../src/inspector/InspectorPanel.tsx";
import { MIXED_TEMPLATE_ID, asBox, buildFacility, buildLayout, columnsFor, conveyorLinks, conveyorRefusal, draftFor, elementFromDrop, linearEndsLinked, snapConveyorEnds, verdictFor } from "../src/workbench/draft.ts";

const placeable = catalog.filter((item) => item.placeable);
if (placeable.length !== 78) throw new Error(`expected 78 placeable, got ${placeable.length}`);
if (catalog.map((item) => item.id).join() !== LIBRARY_IDS.join()) throw new Error("catalog order drifted from LIBRARY_IDS");
const groups = ["IN", "ST", "PK", "CV", "MH", "OUT", "AUX"];
const seen = catalog.map((item) => item.group);
let last = -1;
for (const group of seen) {
  const index = groups.indexOf(group);
  if (index < last) throw new Error(`panel order broke at ${group}`);
  last = index;
}
if (catalog.some((item) => !item.placeable)) throw new Error("library id left grey");
if (catalog.some((item) => item.id !== item.id.toUpperCase() || item.id.includes("_"))) throw new Error("short name leaked into catalog");
for (const id of ["CV-CURVE-01", "CV-MERGE-01", "CV-DIV-01", "CV-BUF-01", "CV-VERT-01", "CV-CHUTE-01", "CV-LOOP-01", "CV-INDUCT-EACH-01", "MH-AGV-01", "ST-ASRS-01", "PK-DEPAL-AUTO-01"]) {
  if (!isUnsimulated(id)) throw new Error(`${id} should stay out of the DES`);
  const item = catalog.find((row) => row.id === id);
  if (!item?.placeable) throw new Error(`${id} must still be draggable`);
}
for (const id of ["CV-STR-01", "CV-ROL-01", "CV-BELT-01"]) {
  if (isUnsimulated(id) || !isLinearConveyor(id)) throw new Error(`${id} must be a simulated straight conveyor`);
  const item = catalog.find((row) => row.id === id);
  if (!item?.placeable) throw new Error(`${id} must still be draggable`);
}
if (isUnsimulated("ST-PAL-01") || isUnsimulated("IN-DOCK-01")) throw new Error("manual types marked unsimulated");
const blocked = unsimulatedMessage(["CV-CURVE-01", "MH-AGV-01", "ST-ASRS-01"]);
if (!blocked.startsWith(copy.unsimulated) || !blocked.includes("CV-CURVE-01") || blocked.includes("CV-STR-01") || blocked.includes("即将")) {
  throw new Error(blocked);
}
if (copy.conveyorIdleNote.includes("已接入")) throw new Error("curve note implies the runtime is connected");
if (JSON.stringify(copy).includes("即将")) throw new Error("copy still says 即将");

const draft = draftFor("mixed");
if (draft.templateId !== MIXED_TEMPLATE_ID) throw new Error(draft.templateId);
const present = new Set(draft.elements.map((el) => el.typeElementId));
for (const id of SLICE11_IDS) {
  if (!present.has(id)) throw new Error(`template missing ${id}`);
}
const blankDrop = draftFor("blank");
for (const item of catalog) {
  const aisleTop = 12 + 3.5 / 2;
  const y = aisleTop + 0.45 + item.widthM / 2;
  const dropped = elementFromDrop([], item.id, 20, y, { id: "n-acc", x: 20, y: 12 });
  if (dropped.lengthM !== item.lengthM || dropped.widthM !== item.widthM || dropped.yawDeg !== item.orientationDeg) {
    throw new Error(`footprint ${item.id} ${dropped.lengthM}x${dropped.widthM}@${dropped.yawDeg}`);
  }
  const verdict = verdictFor(blankDrop, dropped, null);
  if (verdict.tone === "red") throw new Error(`${item.id} refused on blank: ${verdict.reason}`);
}
const buf = elementFromDrop([], "IN-BUF-01", 20, 16, null);
const bufSpan = (yaw) => {
  const corners = footprintCorners(buf.x, buf.y, buf.lengthM, buf.widthM, yaw);
  return Math.max(...corners.map((p) => p.x)) - Math.min(...corners.map((p) => p.x));
};
if (Math.abs(bufSpan(0) - 6) > 1e-6 || Math.abs(bufSpan(90) - 3) > 1e-6) throw new Error("IN-BUF footprint did not follow orientation");
const stg = elementFromDrop([], "OUT-STG-01", 20, 16, null);
const stgSpan = (yaw) => {
  const corners = footprintCorners(stg.x, stg.y, stg.lengthM, stg.widthM, yaw);
  return Math.max(...corners.map((p) => p.x)) - Math.min(...corners.map((p) => p.x));
};
if (Math.abs(stgSpan(0) - stg.lengthM) > 1e-6 || Math.abs(stgSpan(90) - stg.widthM) > 1e-6) {
  throw new Error("OUT-STG footprint did not follow orientation");
}
const boxes = draft.elements.map((el) => ({ id: el.instanceId, box: aabbOf(asBox(el)), el }));
for (const row of boxes) {
  if (!row.el.accessNodeId || row.el.accessX === null) throw new Error(`unbound ${row.id}`);
  if (row.box.minX < -1e-6 || row.box.minY < -1e-6 || row.box.maxX > 40 + 1e-6 || row.box.maxY > 24 + 1e-6) {
    throw new Error(`outside ${row.id} ${JSON.stringify(row.box)}`);
  }
  if (Math.abs(row.el.lengthM) < 0.05) throw new Error(`zero length ${row.id}`);
}
for (let i = 0; i < boxes.length; i += 1) {
  for (let j = i + 1; j < boxes.length; j += 1) {
    const a = boxes[i].box;
    const b = boxes[j].box;
    const hit = !(a.maxX <= b.minX + 1e-6 || b.maxX <= a.minX + 1e-6 || a.maxY <= b.minY + 1e-6 || b.maxY <= a.minY + 1e-6);
    if (hit) throw new Error(`overlap ${boxes[i].id} ${boxes[j].id}`);
  }
}

const rack = draft.elements.find((el) => el.instanceId === "rack-001");
const corners = footprintCorners(rack.x, rack.y, rack.lengthM, rack.widthM, rack.yawDeg);
const span = Math.max(...corners.map((p) => p.x)) - Math.min(...corners.map((p) => p.x));
if (Math.abs(span - 2.7) > 1e-6) throw new Error(`rack length changed with view: ${span}`);
if (rack.lengthM !== 2.7 || rack.widthM !== 1.2 || rack.heightM !== 6) throw new Error("rack metric defaults");

const outside = assessPlacement({
  x: 80,
  y: 80,
  lengthM: 2.7,
  widthM: 1.2,
  yawDeg: 0,
  accessRequired: true,
  storageCopy: true,
  facilityW: 40,
  facilityH: 24,
  aisle: { fromX: 2, toX: 38, y: 12, widthM: 3.5 },
  aisleWidthM: 3.5,
  others: [],
});
if (outside.tone !== "red" || !outside.reason.includes("场地")) throw new Error(outside.reason);
const far = assessPlacement({
  x: 20,
  y: 1,
  lengthM: 2.7,
  widthM: 1.2,
  yawDeg: 0,
  accessRequired: true,
  storageCopy: true,
  facilityW: 40,
  facilityH: 24,
  aisle: { fromX: 2, toX: 38, y: 12, widthM: 3.5 },
  aisleWidthM: 3.5,
  minClearWidthM: 3,
  others: [],
});
if (far.tone !== "red" || !far.reason.includes("接入点")) throw new Error(far.reason);

const blank = draftFor("blank");
const blankNums = [blank.widthM, blank.heightM, blank.aisleWidthM, blank.aisleFromX, blank.aisleToX, blank.aisleY];
if (blank.elements.length !== 0 || blank.templateId !== null) throw new Error("blank should stay empty of devices");
if (blankNums.some((value) => !(Number(value) > 0))) throw new Error(`blank defaults missing ${blankNums.join(",")}`);
const first = elementFromDrop([], "ST-PAL-01", 10, 16, null);
if (first.lengthM !== 2.7 || first.widthM !== 1.2 || first.heightM !== 6) throw new Error("drop defaults");
const seated = verdictFor(blank, first, null);
if (seated.tone === "red") throw new Error(`blank first device refused: ${seated.reason}`);
const narrow = verdictFor({ ...blank, aisleWidthM: "2" }, first, null);
if (narrow.tone !== "red" || !narrow.reason.includes("净宽")) throw new Error(narrow.reason);
const pressed = elementFromDrop([], "ST-PAL-01", 13, 16, null);
const columnHit = verdictFor(blank, pressed, null);
if (columnHit.tone !== "red" || !columnHit.reason.includes("结构柱")) throw new Error(columnHit.reason);

for (const el of draft.elements) {
  if (aabbHits(aabbOf(asBox(el)), FIRE_LANE)) throw new Error(`template sits on fire lane ${el.instanceId}`);
  for (const col of columnsFor(draft)) {
    const gap = boxGap(aabbOf(asBox(el)), columnBox(col));
    if (gap < 0.6) throw new Error(`template ${el.instanceId} gap ${gap} to ${col.id}`);
  }
}
const clean = auditNorms(draft, ["fire-egress", "structure-bay"]);
if (clean.length) throw new Error(`template spec ${JSON.stringify(clean.map((row) => row.message))}`);
if (normSummary("off", [], 0) !== "未选，仅几何硬约束") throw new Error(normSummary("off", [], 0));
if (!normNote("off", []).includes("不能当成消防合规")) throw new Error(normNote("off", []));

const laneCenter = { x: (FIRE_LANE.minX + FIRE_LANE.maxX) / 2, y: (FIRE_LANE.minY + FIRE_LANE.maxY) / 2 };
const occupier = elementFromDrop(draft.elements, "OUT-PACK-01", laneCenter.x, laneCenter.y, null);
const occupied = verdictFor(draft, occupier, null);
if (occupied.tone === "red") throw new Error(`fire lane drop refused: ${occupied.reason}`);
const occupiedDraft = { ...draft, elements: [...draft.elements, occupier] };
const occupiedHits = auditNorms(occupiedDraft, ["fire-egress"]);
const occupy = occupiedHits.find((row) => row.ruleId === "FIRE_OCCUPANCY");
if (!occupy) throw new Error(`expected fire occupancy, got ${JSON.stringify(occupiedHits.map((row) => row.ruleId))}`);
const repaired = applyNormFix(occupiedDraft, occupy);
const after = auditNorms(repaired, ["fire-egress"]);
if (after.some((row) => row.ruleId === "FIRE_OCCUPANCY")) throw new Error(`repair left occupancy ${JSON.stringify(after)}`);

const near = structuredClone(draft);
const nearRack = near.elements.find((el) => el.instanceId === "rack-001");
nearRack.x = 11.2;
const columnFindings = auditNorms(near, ["structure-bay"]);
if (!columnFindings.some((row) => row.ruleId === "COLUMN_PRESS")) throw new Error("expected column press");
const columnFixed = applyNormFix(near, columnFindings[0]);
if (auditNorms(columnFixed, ["structure-bay"]).some((row) => row.id === columnFindings[0].id)) {
  throw new Error("column repair did not clear the finding");
}

const segments = [
  { t0: 0, t1: 10, fromPose: { x: 0, y: 0 }, toPose: { x: 10, y: 0 }, resourceId: "forklift-1", taskId: "T1" },
  { t0: 10, t1: 20, fromPose: { x: 10, y: 0 }, toPose: { x: 10, y: 8 }, resourceId: "forklift-1", taskId: "T1" },
  { t0: 0, t1: 10, fromPose: { x: 1, y: 1 }, toPose: { x: 1, y: 5 }, resourceId: "picker-1", taskId: "T2" },
];
const mid = actorsAt(segments, 5);
if (mid.length !== 2) throw new Error(`actors ${mid.length}`);
const fork = mid.find((actor) => actor.resourceId === "forklift-1");
const picker = mid.find((actor) => actor.resourceId === "picker-1");
if (!fork || Math.abs(fork.x - 5) > 1e-6 || Math.abs(fork.y) > 1e-6) throw new Error(JSON.stringify(fork));
if (!picker || Math.abs(picker.y - 3) > 1e-6) throw new Error(JSON.stringify(picker));
const held = actorsAt(segments, 10);
const heldFork = held.find((actor) => actor.resourceId === "forklift-1");
if (!heldFork || Math.abs(heldFork.x - 10) > 1e-6 || Math.abs(heldFork.y) > 1e-6) throw new Error(JSON.stringify(heldFork));
const bounds = segmentBounds(segments, 3600);
if (bounds.t0 !== 0 || bounds.t1 !== 20) throw new Error(JSON.stringify(bounds));

const ids = Object.keys(EQUIPS);
if (ids.length !== 15) throw new Error(`equip count ${ids.length}`);
for (const id of ids) {
  const equip = EQUIPS[id];
  if (equip.element_id !== id) throw new Error(`element_id ${id}`);
  if (equip.visual?.proxy !== "box" || equip.lod?.lod1 !== "proxy:box" || equip.glb) throw new Error(`proxy flag ${id}`);
  if (!portsNearFootprint(equip)) throw new Error(`ports ${id}`);
  const model = buildFromEquip(equip);
  if (model.badge !== "代理") throw new Error(`badge ${id}`);
  if (model.lengthM <= 0 || model.widthM <= 0 || model.heightM <= 0) throw new Error(`metric ${id}`);
}
const rackEquip = buildFromEquip(EQUIPS["ST-PAL-01"]);
if (Math.abs(rackEquip.lengthM - 13.5) > 1e-6 || Math.abs(rackEquip.widthM - 1.1) > 1e-6 || Math.abs(rackEquip.heightM - 6) > 1e-6) {
  throw new Error(`ST-PAL equip ${rackEquip.lengthM} ${rackEquip.widthM} ${rackEquip.heightM}`);
}
if (rackEquip.seams.filter((seam) => seam.kind === "bay").length < 4) throw new Error("rack bay seams");
if (rackEquip.seams.filter((seam) => seam.kind === "level").length < 3) throw new Error("rack level seams");
const dock = buildFromEquip(EQUIPS["IN-DOCK-01"]);
if (!dock.features.includes("step") || !dock.features.includes("opening")) throw new Error(`dock ${dock.features}`);
const floor = buildFromEquip(EQUIPS["ST-FLOOR-01"]);
if (floor.seams.filter((seam) => seam.kind === "layer").length < 2) throw new Error("floor layers");
const station = buildFromEquip(EQUIPS["PK-STA-01"]);
if (!station.features.includes("tabletop") || station.boxes.filter((box) => box.role === "leg").length !== 4) throw new Error("station");
const hand = buildFromEquip(EQUIPS["MH-HAND-01"]);
if (hand.heightM < 0.05 || hand.heightM > 0.08) throw new Error(`hand height ${hand.heightM}`);
const forkProxy = buildFromEquip(EQUIPS["MH-FORK-01"]);
const placedHand = buildPlaced("MH-HAND-01", { lengthM: 6, widthM: 1.2, heightM: 0.2 });
if (Math.abs(forkProxy.heightM - 0.25) > 1e-6 || forkProxy.widthM <= placedHand.widthM || placedHand.heightM > 0.08) {
  throw new Error(`fork/hand ${forkProxy.heightM} ${forkProxy.widthM} ${placedHand.heightM}`);
}
const bufEquip = buildFromEquip(EQUIPS["IN-BUF-01"]);
if (bufEquip.boxes.filter((box) => box.role === "rail").length < 4) throw new Error("buffer rails");
const full = buildFromEquip(EQUIPS["OUT-FULL-01"]);
if (full.seams.filter((seam) => seam.kind === "bay").length < 3) throw new Error("full bay seams");
const put = buildFromEquip(EQUIPS["PK-PUT-EACH-01"]);
if (put.seams.filter((seam) => seam.kind === "bay").length < 5) throw new Error("putwall bays");
const wall = buildFromEquip(EQUIPS["AUX-WALL-01"]);
if (!wall.features.includes("door")) throw new Error("wall door");
const fire = buildFromEquip(EQUIPS["AUX-FIRE-01"]);
if (fire.heightM > 0.16) throw new Error(`fire height ${fire.heightM}`);
if (PALETTE.dock.fill !== "#A8C5E8" || PALETTE.rack.fill !== "#C5CBD0" || PALETTE.aisle.fillAlpha > 0.3) throw new Error("palette");
const placed = buildPlaced("ST-PAL-01", { lengthM: 2.7, widthM: 1.2, heightM: 6, bays: 1, levels: 4 });
const nearZoom = frameForZoom(placed, 1);
const farZoom = frameForZoom(placed, 3);
if (nearZoom.lengthM !== farZoom.lengthM || nearZoom.widthM !== farZoom.widthM || nearZoom.heightM !== farZoom.heightM) {
  throw new Error("zoom changed meters");
}
if (Math.abs(farZoom.screenLengthPx / farZoom.ppm - placed.lengthM) > 1e-9) throw new Error("screen scale drifted");
const conflict = interactionStyle({ selected: true, conflict: true }, { fill: "#C5CBD0", fillAlpha: 0.4, stroke: "#6E787E", shadowAlpha: 0.08 });
if (conflict.stroke !== "#C44B4B") throw new Error("conflict stroke lost");
const alone = buildPlaced("ST-OVF-01", { lengthM: 4.8, widthM: 2.4, heightM: 1.5 });
if (alone.badge !== "代理" || !alone.features.includes("rail")) throw new Error("fallback proxy");

function decisionHtml(props) {
  return renderToStaticMarkup(
    createElement(RunCards, {
      stale: null,
      simT: 0,
      t0: 0,
      t1: 1,
      playing: false,
      onSimT: () => {},
      onTogglePlay: () => {},
      onBack: () => {},
      summary: "样例",
      children: null,
      ...props,
    }),
  );
}
const refused = decisionHtml({ run: null, rejected: blocked, idleNotice: null });
if (!refused.includes('data-decision-cards="hidden"')) throw new Error("refused cards not hidden");
if (refused.includes('class="kpis"') || refused.includes("托盘吞吐") || refused.includes("—")) {
  throw new Error(`refused decision leaked a card shell: ${refused}`);
}
if (!refused.includes(copy.unsimulated) || !refused.includes("CV-CURVE-01") || !refused.includes("返回编辑")) {
  throw new Error(refused);
}
const idle = decisionHtml({ run: null, rejected: null, idleNotice: copy.notRun });
if (!idle.includes('data-decision-cards="hidden"') || idle.includes('class="kpis"') || idle.includes("—") || !idle.includes("未推演")) {
  throw new Error(idle);
}
const shown = decisionHtml({
  rejected: null,
  idleNotice: null,
  run: {
    cards: {
      throughput: { value: 1 },
      wait: { meanSec: 2, p95Sec: 3, sampleCount: 1 },
      utilization: { byResourceType: [{ resourceType: "forklift", utilization: 0.2 }], byResource: [] },
      bottleneck: { topN: [{ entityId: "e-aisle", waitSec: 2, share: 1 }] },
    },
    secondary: { completionRate: 1, completedTasks: 1, incompleteTasks: 0 },
    layoutRevision: "lr",
    runManifest: { engineVersion: "slice-des-0.1", seedStreams: { demand: 42 } },
    kpiFromUiDemo: false,
  },
});
if (!shown.includes('data-decision-cards="shown"') || !shown.includes('class="kpis"') || !shown.includes("托盘吞吐")) {
  throw new Error("real run hid the four cards");
}

const spanCv = elementFromDrop(draft.elements, "CV-STR-01", 20, 12, { id: "n-acc", x: 20, y: 12 });
if (spanCv.speedMpm !== 30) throw new Error(`straight default speed ${spanCv.speedMpm}`);
spanCv.lengthM = 29;
const shifted = snapConveyorEnds(spanCv, draft.elements);
const placedCv = { ...spanCv, x: shifted.x, y: shifted.y };
const spanLinks = conveyorLinks([placedCv, ...draft.elements]);
if (!linearEndsLinked(placedCv, spanLinks)) {
  throw new Error(`dock span did not link ${JSON.stringify(spanLinks)} @${shifted.x},${shifted.y}`);
}
const openCv = conveyorRefusal({ ...draft, elements: [...draft.elements, { ...spanCv, lengthM: 6, x: 8, y: 4 }] });
if (!openCv.startsWith("输送还没接上") || !openCv.includes("CV-STR-01")) throw new Error(openCv);
const closedCv = conveyorRefusal({ ...draft, elements: [...draft.elements, placedCv] });
if (closedCv) throw new Error(closedCv);
const curveDrop = elementFromDrop(draft.elements, "CV-CURVE-01", 8, 4, { id: "n-acc", x: 8, y: 12 });
if (curveDrop.speedMpm !== 30) throw new Error("curve inspector speed default missing");
const saved = buildLayout({ ...draft, elements: [...draft.elements, placedCv] }, "layout-cv", "pending", { id: "facility-mixed", revision: "pending" });
const savedCv = saved.elements.find((el) => el.typeElementId === "CV-STR-01");
if (!savedCv || savedCv.params.speed_mpm !== 30 || !savedCv.params.conveyorLinks?.length) {
  throw new Error(`layout did not keep speed_mpm and links ${JSON.stringify(savedCv && savedCv.params)}`);
}
function inspectorHtml(selected, elements) {
  return renderToStaticMarkup(
    createElement(InspectorPanel, {
      draft: { ...draft, elements },
      onDraft: () => {},
      selected,
      onElement: () => {},
      fields: {
        fullPallet: true,
        breakBulk: false,
        piecePick: false,
        inbound: "",
        outbound: "",
        shiftHours: "",
        forklifts: "",
        pickers: "",
        travel: "",
        emptySpeed: "",
        pickSec: "",
        shipSec: "",
        windowSec: "",
      },
      onField: () => {},
      onTestValues: () => {},
      testValues: false,
      checks: [],
      prepareReady: null,
      onRecheck: () => {},
      normPhase: "off",
      normSummary: "",
      normNote: "",
      specOn: {},
      findings: [],
      onToggleSpec: () => {},
      onAudit: () => {},
      onFix: () => {},
    }),
  );
}
const straightHtml = inspectorHtml(placedCv, [...draft.elements, placedCv]);
if (!straightHtml.includes("脚印") || !straightHtml.includes('id="speed_mpm"') || !straightHtml.includes("30")) {
  throw new Error("straight inspector hid footprint or speed_mpm");
}
const curveHtml = inspectorHtml(curveDrop, [...draft.elements, curveDrop]);
if (!curveHtml.includes(copy.conveyorIdleNote) || curveHtml.includes("已接入")) {
  throw new Error("curve inspector implies the runtime is connected");
}
const facility = buildFacility(draft, "facility-mixed", "pending");
const layout = buildLayout(draft, "layout-mixed", "pending", { id: "facility-mixed", revision: "pending" });
writeFileSync("/tmp/mixed-slice-facility.json", JSON.stringify(facility));
writeFileSync("/tmp/mixed-slice-layout.json", JSON.stringify(layout));
console.log("LAYOUT UI PASS", `elements=${draft.elements.length}`, `placeable=${placeable.length}`);
process.exit(0);
