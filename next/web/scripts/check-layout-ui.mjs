import { writeFileSync } from "node:fs";
import { footprintCorners, assessPlacement, aabbOf } from "../src/canvas/geom.ts";
import { catalog } from "../src/library/catalog.ts";
import { actorsAt, segmentBounds } from "../src/run-cards/playback.ts";
import { MIXED_TEMPLATE_ID, asBox, buildFacility, buildLayout, draftFor } from "../src/workbench/draft.ts";

const placeable = catalog.filter((item) => item.placeable);
if (placeable.length !== 11) throw new Error(`expected 11 placeable, got ${placeable.length}`);
const grey = catalog.filter((item) => !item.placeable).map((item) => item.id).sort();
const expectedGrey = ["AGV-AMR-01", "ASRS-CRANE-01", "CV-BELT-01"];
if (grey.join() !== expectedGrey.join()) throw new Error(`grey set ${grey.join()}`);

const draft = draftFor("mixed");
if (draft.templateId !== MIXED_TEMPLATE_ID) throw new Error(draft.templateId);
const present = new Set(draft.elements.map((el) => el.typeElementId));
for (const item of placeable) {
  if (!present.has(item.id)) throw new Error(`template missing ${item.id}`);
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

const facility = buildFacility(draft, "facility-mixed", "pending");
const layout = buildLayout(draft, "layout-mixed", "pending", { id: "facility-mixed", revision: "pending" });
writeFileSync("/tmp/mixed-slice-facility.json", JSON.stringify(facility));
writeFileSync("/tmp/mixed-slice-layout.json", JSON.stringify(layout));
console.log("LAYOUT UI PASS", `elements=${draft.elements.length}`, `placeable=${placeable.length}`);
