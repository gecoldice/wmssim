/** Meter geometry shared by the canvas ghost, snap, and access binding. */

export const MAX_ACCESS_M = 8;

export type Tone = "green" | "yellow" | "red";

export type Pt = { x: number; y: number };

export type BoxEl = {
  instanceId: string;
  x: number;
  y: number;
  yawDeg: number;
  lengthM: number;
  widthM: number;
  /** Fire lanes are occupancy zones: overlap is a warning, not a solid collision. */
  fireZone?: boolean;
};

export type ColumnMark = { id: string; x: number; y: number; sizeM: number };

/** Touching a column face counts as pressing it. */
export const COLUMN_PRESS_GAP_M = 0.02;
/** Spec pack: keep this gap off the column face. Geometry still allows a closer yellow drop. */
export const COLUMN_SPEC_CLEAR_M = 0.6;
/** Geometry floor when a device eats the aisle and does not declare its own minimum. */
export const GEOMETRY_CLEAR_FLOOR_M = 1.2;
/** Fire-egress pack: main aisle clear width. */
export const FIRE_AISLE_MIN_M = 2.4;

/** South band kept for the fire-egress pack. Not a solid and not a server obstacle. */
export const FIRE_LANE: Aabb = { minX: 11.2, minY: 3.6, maxX: 16.8, maxY: 6.2 };

export const DEFAULT_COLUMNS: ColumnMark[] = [
  { id: "col-1", x: 13, y: 16, sizeM: 0.5 },
  { id: "col-2", x: 3.2, y: 3.2, sizeM: 0.5 },
  { id: "col-3", x: 22.5, y: 3.2, sizeM: 0.5 },
  { id: "col-4", x: 37, y: 21, sizeM: 0.5 },
];

export type AisleLine = {
  fromX: number;
  toX: number;
  y: number;
  widthM: number;
};

export type Guide = { x1: number; y1: number; x2: number; y2: number };

export type AccessHit = { x: number; y: number; dist: number; id: string };

export type Verdict = {
  tone: Tone;
  reason: string;
  access: AccessHit | null;
};

export function quantMeter(value: number): number {
  return Math.round(value * 20) / 20;
}

export function footprintCorners(cx: number, cy: number, lengthM: number, widthM: number, yawDeg: number): Pt[] {
  const yaw = (yawDeg * Math.PI) / 180;
  const cos = Math.cos(yaw);
  const sin = Math.sin(yaw);
  const hw = lengthM / 2;
  const hd = widthM / 2;
  return [
    [-hw, -hd],
    [hw, -hd],
    [hw, hd],
    [-hw, hd],
  ].map(([lx, ly]) => ({
    x: cx + lx * cos - ly * sin,
    y: cy + lx * sin + ly * cos,
  }));
}

export function localToWorld(cx: number, cy: number, yawDeg: number, lx: number, ly: number): Pt {
  const yaw = (yawDeg * Math.PI) / 180;
  const cos = Math.cos(yaw);
  const sin = Math.sin(yaw);
  return { x: cx + lx * cos - ly * sin, y: cy + lx * sin + ly * cos };
}

export type Aabb = { minX: number; minY: number; maxX: number; maxY: number };

export function cornersAabb(corners: Pt[]): Aabb {
  const xs = corners.map((p) => p.x);
  const ys = corners.map((p) => p.y);
  return { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) };
}

export function aabbOf(el: BoxEl): Aabb {
  return cornersAabb(footprintCorners(el.x, el.y, el.lengthM, el.widthM, el.yawDeg));
}

export function aabbHits(a: Aabb, b: Aabb, eps = 1e-6): boolean {
  return !(a.maxX <= b.minX + eps || b.maxX <= a.minX + eps || a.maxY <= b.minY + eps || b.maxY <= a.minY + eps);
}

function intersects(a: Aabb, b: Aabb, eps = 1e-6): boolean {
  return aabbHits(a, b, eps);
}

export function columnBox(col: ColumnMark): Aabb {
  const half = col.sizeM / 2;
  return { minX: col.x - half, minY: col.y - half, maxX: col.x + half, maxY: col.y + half };
}

/** 0 when the boxes touch or overlap. Positive when a gap remains. */
export function boxGap(a: Aabb, b: Aabb): number {
  const dx = Math.max(b.minX - a.maxX, a.minX - b.maxX);
  const dy = Math.max(b.minY - a.maxY, a.minY - b.maxY);
  if (dx <= 0 && dy <= 0) return 0;
  return Math.hypot(Math.max(dx, 0), Math.max(dy, 0));
}

export function fireLaneInside(width: number, height: number): Aabb | null {
  if (FIRE_LANE.minX >= -1e-6 && FIRE_LANE.minY >= -1e-6 && FIRE_LANE.maxX <= width + 1e-6 && FIRE_LANE.maxY <= height + 1e-6) {
    return FIRE_LANE;
  }
  return null;
}

/** Remaining vertical gap inside a horizontal aisle after this footprint clips it. */
export function aisleRemainingClear(aisle: AisleLine, box: Aabb): number | null {
  const band: Aabb = {
    minX: Math.min(aisle.fromX, aisle.toX),
    maxX: Math.max(aisle.fromX, aisle.toX),
    minY: aisle.y - aisle.widthM / 2,
    maxY: aisle.y + aisle.widthM / 2,
  };
  if (!intersects(box, band)) return null;
  const coverLo = Math.max(band.minY, box.minY);
  const coverHi = Math.min(band.maxY, box.maxY);
  const below = Math.max(0, coverLo - band.minY);
  const above = Math.max(0, band.maxY - coverHi);
  return Math.max(below, above);
}

function inside(a: Aabb, b: Aabb, eps = 1e-6): boolean {
  return a.minX >= b.minX - eps && a.minY >= b.minY - eps && a.maxX <= b.maxX + eps && a.maxY <= b.maxY + eps;
}

function grow(box: Aabb, pad: number): Aabb {
  return { minX: box.minX - pad, minY: box.minY - pad, maxX: box.maxX + pad, maxY: box.maxY + pad };
}

export function projectAccess(x: number, y: number, aisle: AisleLine | null): AccessHit | null {
  if (!aisle) return null;
  const lo = Math.min(aisle.fromX, aisle.toX);
  const hi = Math.max(aisle.fromX, aisle.toX);
  const ax = Math.min(hi, Math.max(lo, x));
  const ay = aisle.y;
  const dist = Math.hypot(x - ax, y - ay);
  if (dist > MAX_ACCESS_M) return null;
  const qx = quantMeter(ax);
  const qy = quantMeter(ay);
  return {
    x: qx,
    y: qy,
    dist,
    id: `n-acc-${Math.round(qx * 100)}-${Math.round(qy * 100)}`,
  };
}

export function snapCenter(
  rawX: number,
  rawY: number,
  aisle: AisleLine | null,
  others: BoxEl[],
  lengthM: number,
  widthM: number,
  yawDeg: number,
  facilityW: number,
  facilityH: number,
): { x: number; y: number; guides: Guide[] } {
  let x = rawX;
  let y = rawY;
  const guides: Guide[] = [];
  const xTol = 0.45;
  const yTol = 0.45;
  let yLocked = false;

  if (aisle && Math.abs(rawY - aisle.y) <= 0.6) {
    y = aisle.y;
    yLocked = true;
    guides.push({ x1: Math.min(aisle.fromX, aisle.toX), y1: aisle.y, x2: Math.max(aisle.fromX, aisle.toX), y2: aisle.y });
  }
  if (aisle) {
    const marks = [aisle.fromX, aisle.toX, (aisle.fromX + aisle.toX) / 2];
    for (const mark of marks) {
      if (Math.abs(rawX - mark) <= 0.6) {
        x = mark;
        guides.push({ x1: mark, y1: 0, x2: mark, y2: facilityH });
        break;
      }
    }
  }

  const self = cornersAabb(footprintCorners(rawX, rawY, lengthM, widthM, yawDeg));
  let bestDx = 0;
  let bestAbsX = xTol;
  let guideX = 0;
  let haveX = false;
  let bestDy = 0;
  let bestAbsY = yTol;
  let guideY = 0;
  let haveY = false;
  for (const other of others) {
    const box = aabbOf(other);
    const xPairs: Array<[number, number]> = [
      [self.minX, box.minX],
      [self.minX, box.maxX],
      [self.maxX, box.minX],
      [self.maxX, box.maxX],
      [rawX, other.x],
    ];
    for (const [from, to] of xPairs) {
      const delta = to - from;
      if (Math.abs(delta) < bestAbsX) {
        bestAbsX = Math.abs(delta);
        bestDx = delta;
        guideX = to;
        haveX = true;
      }
    }
    const yPairs: Array<[number, number]> = [
      [self.minY, box.minY],
      [self.minY, box.maxY],
      [self.maxY, box.minY],
      [self.maxY, box.maxY],
      [rawY, other.y],
    ];
    for (const [from, to] of yPairs) {
      const delta = to - from;
      if (Math.abs(delta) < bestAbsY) {
        bestAbsY = Math.abs(delta);
        bestDy = delta;
        guideY = to;
        haveY = true;
      }
    }
  }
  if (haveX) {
    x = rawX + bestDx;
    guides.push({ x1: guideX, y1: 0, x2: guideX, y2: facilityH });
  } else if (!guides.some((guide) => guide.x1 === guide.x2)) {
    const grid = quantMeter(Math.round(rawX * 2) / 2);
    if (Math.abs(grid - rawX) <= 0.2) x = grid;
  }
  if (!yLocked && haveY) {
    y = rawY + bestDy;
    guides.push({ x1: 0, y1: guideY, x2: facilityW, y2: guideY });
  } else if (!yLocked) {
    const grid = quantMeter(Math.round(rawY * 2) / 2);
    if (Math.abs(grid - rawY) <= 0.2) y = grid;
  }
  return { x: quantMeter(x), y: quantMeter(y), guides };
}

export function assessPlacement(input: {
  x: number;
  y: number;
  lengthM: number;
  widthM: number;
  yawDeg: number;
  accessRequired: boolean;
  storageCopy: boolean;
  facilityW: number | null;
  facilityH: number | null;
  aisle: AisleLine | null;
  aisleWidthM: number | null;
  minClearWidthM?: number;
  /** Docks and the fire lane itself may sit in the aisle. */
  encroach?: boolean;
  columns?: ColumnMark[];
  fireLane?: Aabb | null;
  others: BoxEl[];
}): Verdict {
  const { x, y, lengthM, widthM, yawDeg } = input;
  if (input.facilityW === null || input.facilityH === null || input.facilityW <= 0 || input.facilityH <= 0) {
    return { tone: "red", reason: "场地宽和高未填写，不能放下。", access: null };
  }
  const box = cornersAabb(footprintCorners(x, y, lengthM, widthM, yawDeg));
  const facility = { minX: 0, minY: 0, maxX: input.facilityW, maxY: input.facilityH };
  if (!inside(box, facility)) {
    return { tone: "red", reason: "占地超出场地边界。", access: null };
  }
  for (const other of input.others) {
    if (other.fireZone) continue;
    if (intersects(box, aabbOf(other))) {
      return { tone: "red", reason: `与 ${other.instanceId} 占地重叠。`, access: null };
    }
  }
  for (const col of input.columns ?? []) {
    const gap = boxGap(box, columnBox(col));
    if (gap <= COLUMN_PRESS_GAP_M) {
      return { tone: "red", reason: `压住结构柱 ${col.id}，不能放下。挪开再松手。`, access: null };
    }
  }
  const access = projectAccess(x, y, input.aisle);
  if (input.accessRequired && !access) {
    const reason = input.storageCopy
      ? "没有可绑定的接入点。请把货架或地堆放到通道中心线 8 米以内后再松手。"
      : "没有可绑定的接入点。请放到通道中心线 8 米以内后再松手，否则准备不能通过。";
    return { tone: "red", reason, access: null };
  }
  if (
    input.minClearWidthM !== undefined &&
    input.aisleWidthM !== null &&
    input.aisleWidthM + 1e-9 < input.minClearWidthM
  ) {
    return {
      tone: "red",
      reason: `通道净宽不足：现在 ${input.aisleWidthM} 米，这台设备至少要 ${input.minClearWidthM} 米。加宽通道后再放下。`,
      access,
    };
  }
  if (input.encroach !== false && input.aisle) {
    const remain = aisleRemainingClear(input.aisle, box);
    const need = input.minClearWidthM ?? GEOMETRY_CLEAR_FLOOR_M;
    if (remain !== null && remain + 1e-9 < need) {
      return {
        tone: "red",
        reason: `通道净宽不足：放下后主通道只剩 ${remain.toFixed(1)} 米，至少要 ${need} 米。往通道外挪再松手。`,
        access,
      };
    }
  }
  const notes: string[] = [];
  if (input.fireLane && intersects(box, input.fireLane)) {
    notes.push("占住消防疏散带。勾选消防疏散并校核后不能推演");
  }
  for (const col of input.columns ?? []) {
    const gap = boxGap(box, columnBox(col));
    if (gap > COLUMN_PRESS_GAP_M && gap < COLUMN_SPEC_CLEAR_M) {
      notes.push(`距结构柱 ${col.id} 只有 ${gap.toFixed(1)} 米`);
    }
  }
  if (access && access.dist > 5) notes.push(`距通道中心 ${access.dist.toFixed(1)} 米`);
  const edgePad = 0.35;
  if (
    box.minX < edgePad ||
    box.minY < edgePad ||
    input.facilityW - box.maxX < edgePad ||
    input.facilityH - box.maxY < edgePad
  ) {
    notes.push("贴近场地边界");
  }
  for (const other of input.others) {
    if (other.fireZone) continue;
    if (intersects(grow(box, 0.3), aabbOf(other))) {
      notes.push(`与 ${other.instanceId} 间距小于 0.3 米`);
      break;
    }
  }
  if (notes.length) {
    return { tone: "yellow", reason: notes.join("；"), access };
  }
  return {
    tone: "green",
    reason: access ? `可放入，接入 ${access.id}` : "可放入",
    access,
  };
}
