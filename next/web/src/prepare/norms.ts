/** Spec-pack audit. Geometry hard checks stay in assessPlacement; this only runs after 「按规范校核」. */

import {
  COLUMN_PRESS_GAP_M,
  COLUMN_SPEC_CLEAR_M,
  FIRE_AISLE_MIN_M,
  aabbHits,
  aabbOf,
  aisleRemainingClear,
  boxGap,
  columnBox,
  fireLaneInside,
  quantMeter,
  type Aabb,
} from "../canvas/geom";
import { catalogItem } from "../library/catalog";
import { aisleOf, asBox, columnsFor, parseNum, siteDefaults, verdictFor, type Draft, type PoseEl } from "../workbench/draft";

export const SPEC_PACKS = [
  { id: "fire-egress" as const, name: "消防疏散默认", hint: "主通道净宽、消防占位" },
  { id: "structure-bay" as const, name: "建筑净空柱距", hint: "压柱、柱边净距" },
];

export type SpecPackId = (typeof SPEC_PACKS)[number]["id"];

export type NormPhase = "off" | "stale" | "fail" | "pass";

export type NormRepair =
  | { kind: "aisle"; widthM: number }
  | { kind: "move"; instanceId: string; x: number; y: number };

export type NormFinding = {
  id: string;
  packId: SpecPackId;
  ruleId: "CLEAR_WIDTH" | "COLUMN_PRESS" | "FIRE_OCCUPANCY";
  title: string;
  message: string;
  objectIds: string[];
  columnIds: string[];
  aisle: boolean;
  fireLane: boolean;
  fixLabel: string;
  repair: NormRepair | null;
};

const AISLE_FACE = new Set(["IN-DOCK-01", "OUT-DOCK-01", "AUX-FIRE-01"]);

export function normKeyOf(draft: Draft, selected: SpecPackId[]): string {
  return JSON.stringify({
    selected: [...selected].sort(),
    site: [draft.widthM, draft.heightM, draft.aisleWidthM, draft.aisleFromX, draft.aisleToX, draft.aisleY],
    elements: draft.elements.map((el) => [
      el.instanceId,
      el.typeElementId,
      el.x,
      el.y,
      el.yawDeg,
      el.lengthM,
      el.widthM,
      el.heightM,
    ]),
  });
}

export function normSummary(phase: NormPhase, selected: SpecPackId[], hardCount: number): string {
  if (phase === "off" || selected.length === 0) return "未选，仅几何硬约束";
  const n = selected.length;
  if (phase === "stale") return `已选 ${n} 包 / 尚未校核`;
  if (phase === "fail") return `已选 ${n} 包 / 硬冲突 ${hardCount} 条`;
  return `已选 ${n} 包 / 校核通过`;
}

export function normNote(phase: NormPhase, selected: SpecPackId[]): string {
  if (!selected.includes("fire-egress")) return "未勾选消防疏散，不能当成消防合规。";
  if (phase === "pass") return "消防疏散默认已校核，这一包没有硬冲突。";
  if (phase === "fail") return "消防疏散默认有硬冲突，不能推演。";
  return "消防疏散默认已勾选，校核前不能推演。";
}

export function auditNorms(draft: Draft, selected: SpecPackId[]): NormFinding[] {
  const findings: NormFinding[] = [];
  if (selected.includes("fire-egress")) findings.push(...auditFire(draft));
  if (selected.includes("structure-bay")) findings.push(...auditStructure(draft));
  return findings;
}

export function applyNormFix(draft: Draft, finding: NormFinding): Draft {
  if (!finding.repair) return draft;
  if (finding.repair.kind === "aisle") {
    const site = siteDefaults();
    return {
      ...draft,
      aisleWidthM: String(finding.repair.widthM),
      aisleFromX: draft.aisleFromX.trim() ? draft.aisleFromX : site.aisleFromX,
      aisleToX: draft.aisleToX.trim() ? draft.aisleToX : site.aisleToX,
      aisleY: draft.aisleY.trim() ? draft.aisleY : site.aisleY,
    };
  }
  const { instanceId, x, y } = finding.repair;
  return {
    ...draft,
    elements: draft.elements.map((el) => (el.instanceId === instanceId ? { ...el, x, y } : el)),
  };
}

function auditFire(draft: Draft): NormFinding[] {
  const out: NormFinding[] = [];
  const aisle = aisleOf(draft);
  const need = Math.max(FIRE_AISLE_MIN_M, ...draft.elements.map((el) => el.minClearWidthM ?? 0));
  if (!aisle || aisle.widthM + 1e-9 < FIRE_AISLE_MIN_M) {
    const width = aisle ? aisle.widthM : 0;
    out.push({
      id: "fire-clear-width",
      packId: "fire-egress",
      ruleId: "CLEAR_WIDTH",
      title: "通道净宽不足",
      message: aisle
        ? `通道净宽不足：主通道现在 ${width} 米，消防疏散至少要 ${FIRE_AISLE_MIN_M} 米。`
        : "通道净宽不足：还没有主通道，消防疏散无法量净宽。",
      objectIds: ["aisle-main"],
      columnIds: [],
      aisle: true,
      fireLane: false,
      fixLabel: `把通道宽改成 ${need} 米`,
      repair: { kind: "aisle", widthM: need },
    });
  }
  if (aisle) {
    for (const el of draft.elements) {
      if (AISLE_FACE.has(el.typeElementId)) continue;
      const remain = aisleRemainingClear(aisle, aabbOf(asBox(el)));
      if (remain === null || remain + 1e-9 >= FIRE_AISLE_MIN_M) continue;
      const moved = searchMove(draft, el, (box) => {
        const next = aisleRemainingClear(aisle, box);
        return next === null || next + 1e-9 >= FIRE_AISLE_MIN_M;
      });
      out.push({
        id: `fire-encroach-${el.instanceId}`,
        packId: "fire-egress",
        ruleId: "CLEAR_WIDTH",
        title: "通道净宽不足",
        message: `通道净宽不足：${labelOf(el)}挤进主通道，剩下约 ${remain.toFixed(1)} 米，消防疏散至少要 ${FIRE_AISLE_MIN_M} 米。`,
        objectIds: [el.instanceId, "aisle-main"],
        columnIds: [],
        aisle: true,
        fireLane: false,
        fixLabel: "把设备挪出通道",
        repair: moved,
      });
    }
  }
  const lane = laneOf(draft);
  if (lane) {
    for (const el of draft.elements) {
      if (el.typeElementId === "AUX-FIRE-01") continue;
      if (!aabbHits(aabbOf(asBox(el)), lane)) continue;
      const moved = searchMove(draft, el, (box) => !aabbHits(box, lane));
      out.push({
        id: `fire-occupy-${el.instanceId}`,
        packId: "fire-egress",
        ruleId: "FIRE_OCCUPANCY",
        title: "占用消防疏散带",
        message: `${labelOf(el)}占住了消防疏散带。挪开后这一包才能过，取消勾选则只按几何硬约束推演。`,
        objectIds: [el.instanceId],
        columnIds: [],
        aisle: false,
        fireLane: true,
        fixLabel: "挪出消防疏散带",
        repair: moved,
      });
    }
  }
  return out;
}

function auditStructure(draft: Draft): NormFinding[] {
  const out: NormFinding[] = [];
  for (const el of draft.elements) {
    for (const col of columnsFor(draft)) {
      const gap = boxGap(aabbOf(asBox(el)), columnBox(col));
      if (gap + 1e-9 >= COLUMN_SPEC_CLEAR_M) continue;
      const pressed = gap <= COLUMN_PRESS_GAP_M;
      const moved = searchMove(draft, el, (box) => boxGap(box, columnBox(col)) + 1e-9 >= COLUMN_SPEC_CLEAR_M);
      out.push({
        id: `column-${el.instanceId}-${col.id}`,
        packId: "structure-bay",
        ruleId: "COLUMN_PRESS",
        title: pressed ? "压住结构柱" : "贴柱过近",
        message: pressed
          ? `${labelOf(el)}压住结构柱 ${col.id}。挪开才能过建筑净空柱距。`
          : `${labelOf(el)}距结构柱 ${col.id} 只有 ${gap.toFixed(1)} 米，柱边净距要 ${COLUMN_SPEC_CLEAR_M} 米，按压柱处理。`,
        objectIds: [el.instanceId],
        columnIds: [col.id],
        aisle: false,
        fireLane: false,
        fixLabel: "挪离结构柱",
        repair: moved,
      });
    }
  }
  return out;
}

function laneOf(draft: Draft): Aabb | null {
  const width = parseNum(draft.widthM);
  const height = parseNum(draft.heightM);
  if (width === null || height === null) return null;
  return fireLaneInside(width, height);
}

function labelOf(el: PoseEl): string {
  const name = catalogItem(el.typeElementId)?.name ?? el.typeElementId;
  return `${name} ${el.instanceId} `;
}

function searchMove(draft: Draft, el: PoseEl, goal: (box: Aabb) => boolean): NormRepair | null {
  const dirs = [
    { x: 0, y: 1 },
    { x: 0, y: -1 },
    { x: 1, y: 0 },
    { x: -1, y: 0 },
    { x: 1, y: 1 },
    { x: -1, y: 1 },
    { x: 1, y: -1 },
    { x: -1, y: -1 },
  ];
  for (const dir of dirs) {
    const len = Math.hypot(dir.x, dir.y) || 1;
    for (let step = 0.4; step <= 6.01; step += 0.4) {
      const x = quantMeter(el.x + (dir.x / len) * step);
      const y = quantMeter(el.y + (dir.y / len) * step);
      const candidate: PoseEl = { ...el, x, y };
      if (verdictFor(draft, candidate, el.instanceId).tone === "red") continue;
      if (!goal(aabbOf(asBox(candidate)))) continue;
      return { kind: "move", instanceId: el.instanceId, x, y };
    }
  }
  return null;
}

