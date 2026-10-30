/** Shared document builders. Blank, rectangle, and mixed starts all use these functions. */

import {
  assessPlacement,
  columnBox,
  DEFAULT_COLUMNS,
  fireLaneInside,
  footprintCorners,
  projectAccess,
  type AisleLine,
  type BoxEl,
  type ColumnMark,
} from "../canvas/geom";
import { catalogItem, instancePrefix, isLinearConveyor, isPlaceable, type CatalogItem } from "../library/catalog";

export const MIXED_TEMPLATE_ID = "template.mixed_wh_v0";

export type PlaceableType = string;

export type PoseEl = {
  instanceId: string;
  typeElementId: PlaceableType;
  x: number;
  y: number;
  yawDeg: number;
  lengthM: number;
  widthM: number;
  heightM: number;
  accessNodeId: string | null;
  accessX: number | null;
  accessY: number | null;
  bays?: number;
  levels?: number;
  palletsPerBay?: number;
  minClearWidthM?: number;
  /** Formal conveyor speed. Undefined uses the type default; null means the user cleared it. */
  speedMpm?: number | null;
  throughputUph?: number | null;
  maxLoadKg?: number | null;
  direction?: string | null;
  allowLoadTypes?: string[] | null;
};

export type Draft = {
  templateId: string | null;
  widthM: string;
  heightM: string;
  aisleWidthM: string;
  aisleFromX: string;
  aisleToX: string;
  aisleY: string;
  elements: PoseEl[];
};

export type ScenarioFields = {
  fullPallet: boolean;
  breakBulk: boolean;
  piecePick: boolean;
  inbound: string;
  outbound: string;
  shiftHours: string;
  forklifts: string;
  pickers: string;
  travel: string;
  emptySpeed: string;
  pickSec: string;
  shipSec: string;
  windowSec: string;
};

const EVIDENCE = {
  sourceKind: "manual",
  sourceRef: "workbench",
  confirmationStatus: "confirmed",
  updatedAt: "2026-10-29T00:00:00+00:00",
};

/** Starter meters so a blank sheet can take the first device without typing six sizes. */
export function siteDefaults(): Pick<Draft, "widthM" | "heightM" | "aisleWidthM" | "aisleFromX" | "aisleToX" | "aisleY"> {
  return {
    widthM: "40",
    heightM: "24",
    aisleWidthM: "3.5",
    aisleFromX: "2",
    aisleToX: "38",
    aisleY: "12",
  };
}

export function draftFor(mode: "blank" | "rectangle" | "mixed"): Draft {
  if (mode === "mixed") return mixedWarehouse();
  return { templateId: null, ...siteDefaults(), elements: [] };
}

function shell(partial: Omit<PoseEl, "accessNodeId" | "accessX" | "accessY">): PoseEl {
  return { ...partial, accessNodeId: null, accessX: null, accessY: null };
}

function fromCatalog(
  instanceId: string,
  type: PlaceableType,
  x: number,
  y: number,
  overrides: Partial<Pick<PoseEl, "yawDeg" | "lengthM" | "widthM" | "heightM" | "bays" | "levels">> = {},
): PoseEl {
  const spec = catalogItem(type);
  if (!spec || !spec.placeable) throw new Error(`不可放置 ${type}`);
  const bays = overrides.bays ?? spec.defaultBays;
  const levels = overrides.levels ?? spec.defaultLevels;
  const lengthM =
    overrides.lengthM ??
    (spec.bayLengthM && bays ? spec.bayLengthM * bays : spec.lengthM);
  const heightM =
    overrides.heightM ?? (spec.levelHeightM && levels ? spec.levelHeightM * levels : spec.heightM);
  return shell({
    instanceId,
    typeElementId: type,
    x,
    y,
    yawDeg: overrides.yawDeg ?? spec.orientationDeg,
    lengthM,
    widthM: overrides.widthM ?? spec.widthM,
    heightM,
    bays,
    levels,
    palletsPerBay: spec.palletsPerBay,
    minClearWidthM: spec.minClearWidthM,
  });
}

/** Comprehensive warehouse with the manual-path devices already seated. */
function mixedWarehouse(): Draft {
  const draft: Draft = {
    templateId: MIXED_TEMPLATE_ID,
    ...siteDefaults(),
    elements: [
      fromCatalog("dock-in", "IN-DOCK-01", 4, 12),
      fromCatalog("dock-out", "OUT-DOCK-01", 36, 12),
      fromCatalog("rack-001", "ST-PAL-01", 10, 16),
      fromCatalog("rack-002", "ST-PAL-01", 16, 16),
      fromCatalog("floor-001", "ST-FLOOR-01", 26, 16.4),
      fromCatalog("depal-001", "PK-DEPAL-01", 9, 7.6),
      fromCatalog("put-001", "PK-PUT-EACH-01", 18, 7.8),
      fromCatalog("pack-001", "OUT-PACK-01", 26, 7.6),
      fromCatalog("hand-001", "MH-HAND-01", 14, 14.35),
      fromCatalog("fork-001", "MH-FORK-01", 33.2, 7.4),
      fromCatalog("fire-001", "AUX-FIRE-01", 33, 4.6, { lengthM: 8 }),
      fromCatalog("wall-001", "AUX-WALL-01", 20, 19.5, { lengthM: 22 }),
    ],
  };
  return rebindAccess(draft).draft;
}

const AISLE_FACE = new Set(["IN-DOCK-01", "OUT-DOCK-01", "AUX-FIRE-01"]);

export function columnsFor(draft: Draft): ColumnMark[] {
  const width = parseNum(draft.widthM);
  const height = parseNum(draft.heightM);
  if (width === null || height === null || width <= 0 || height <= 0) return [];
  return DEFAULT_COLUMNS.filter((col) => {
    const box = columnBox(col);
    return box.minX >= -1e-6 && box.minY >= -1e-6 && box.maxX <= width + 1e-6 && box.maxY <= height + 1e-6;
  });
}

export function aisleOf(draft: Draft): AisleLine | null {
  const fromX = parseNum(draft.aisleFromX);
  const toX = parseNum(draft.aisleToX);
  const y = parseNum(draft.aisleY);
  const widthM = parseNum(draft.aisleWidthM);
  if (fromX === null || toX === null || y === null || widthM === null) return null;
  return { fromX, toX, y, widthM };
}

export type ConveyorLink = {
  fromInstanceId: string;
  fromPort: string;
  toInstanceId: string;
  toPort: string;
};

const PORT_TOL_M = 0.05;
const PORT_SNAP_M = 0.2;

export function conveyorEnds(el: PoseEl): Array<{ role: "in" | "out"; x: number; y: number }> {
  const yaw = (el.yawDeg * Math.PI) / 180;
  const dx = Math.cos(yaw);
  const dy = Math.sin(yaw);
  const half = el.lengthM / 2;
  return [
    { role: "in", x: el.x - dx * half, y: el.y - dy * half },
    { role: "out", x: el.x + dx * half, y: el.y + dy * half },
  ];
}

function closestOnFootprint(el: PoseEl, px: number, py: number): { x: number; y: number; d: number; along: number } {
  const corners = footprintCorners(el.x, el.y, el.lengthM, el.widthM, el.yawDeg);
  let best = { x: el.x, y: el.y, d: Infinity, along: 1 };
  for (let i = 0; i < corners.length; i += 1) {
    const a = corners[i];
    const b = corners[(i + 1) % corners.length];
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const len2 = abx * abx + aby * aby;
    const t = len2 <= 1e-12 ? 0 : Math.max(0, Math.min(1, ((px - a.x) * abx + (py - a.y) * aby) / len2));
    const x = a.x + abx * t;
    const y = a.y + aby * t;
    const d = Math.hypot(x - px, y - py);
    const edge = Math.hypot(abx, aby) || 1;
    const along = Math.abs((Math.cos((el.yawDeg * Math.PI) / 180) * abx + Math.sin((el.yawDeg * Math.PI) / 180) * aby) / edge);
    if (d < best.d) best = { x, y, d, along };
  }
  return best;
}

function headOn(conveyor: PoseEl, endRole: "in" | "out", other: PoseEl, hit: { along: number }): boolean {
  const yaw = (conveyor.yawDeg * Math.PI) / 180;
  const axisX = Math.cos(yaw);
  const axisY = Math.sin(yaw);
  const vx = other.x - conveyor.x;
  const vy = other.y - conveyor.y;
  const vlen = Math.hypot(vx, vy) || 1;
  const facing = endRole === "out" ? 1 : -1;
  const align = (facing * (axisX * vx + axisY * vy)) / vlen;
  return align >= Math.cos((5 * Math.PI) / 180) && hit.along <= Math.sin((5 * Math.PI) / 180) + 1e-6;
}

export function snapConveyorEnds(el: PoseEl, others: PoseEl[]): { x: number; y: number } {
  if (!isLinearConveyor(el.typeElementId)) return { x: el.x, y: el.y };
  let best: { dx: number; dy: number; d: number } | null = null;
  for (const end of conveyorEnds(el)) {
    for (const other of others) {
      if (other.instanceId === el.instanceId) continue;
      const hit = closestOnFootprint(other, end.x, end.y);
      if (hit.d > PORT_SNAP_M || !headOn(el, end.role, other, hit)) continue;
      if (!best || hit.d < best.d) best = { dx: hit.x - end.x, dy: hit.y - end.y, d: hit.d };
    }
  }
  if (!best) return { x: el.x, y: el.y };
  return { x: el.x + best.dx, y: el.y + best.dy };
}

export function conveyorLinks(elements: PoseEl[]): ConveyorLink[] {
  const links: ConveyorLink[] = [];
  for (const el of elements) {
    if (!isLinearConveyor(el.typeElementId)) continue;
    for (const end of conveyorEnds(el)) {
      let best: { other: PoseEl; d: number; along: number } | null = null;
      for (const other of elements) {
        if (other.instanceId === el.instanceId) continue;
        const hit = closestOnFootprint(other, end.x, end.y);
        if (hit.d > PORT_TOL_M || !headOn(el, end.role, other, hit)) continue;
        if (!best || hit.d < best.d) best = { other, d: hit.d, along: hit.along };
      }
      if (!best) continue;
      const neighborPort = `cv_${el.instanceId}_${end.role}`;
      if (end.role === "in") {
        links.push({
          fromInstanceId: best.other.instanceId,
          fromPort: neighborPort,
          toInstanceId: el.instanceId,
          toPort: "p_in",
        });
      } else {
        links.push({
          fromInstanceId: el.instanceId,
          fromPort: "p_out",
          toInstanceId: best.other.instanceId,
          toPort: neighborPort,
        });
      }
    }
  }
  return links;
}

export function linearEndsLinked(el: PoseEl, links: ConveyorLink[]): boolean {
  const inn = links.some((link) => link.toInstanceId === el.instanceId && link.toPort === "p_in");
  const out = links.some((link) => link.fromInstanceId === el.instanceId && link.fromPort === "p_out");
  return inn && out;
}

export function conveyorRefusal(draft: Draft): string {
  const linear = draft.elements.filter((el) => isLinearConveyor(el.typeElementId));
  if (!linear.length) return "";
  const missing: string[] = [];
  for (const el of linear) {
    const names: string[] = [];
    if (!(el.lengthM > 0)) names.push("长度");
    if (!(el.widthM > 0)) names.push("宽度");
    const speed = el.speedMpm === undefined ? 30 : el.speedMpm;
    const throughput = el.throughputUph === undefined ? 120 : el.throughputUph;
    const load = el.maxLoadKg === undefined ? 1500 : el.maxLoadKg;
    const direction = el.direction === undefined ? "forward" : el.direction;
    const loads = el.allowLoadTypes === undefined ? ["pallet"] : el.allowLoadTypes;
    if (speed === null || !(speed > 0)) names.push("速度");
    if (throughput === null || !(throughput > 0)) names.push("吞吐");
    if (load === null || !(load > 0)) names.push("载重");
    if (!direction) names.push("方向");
    if (!loads || !loads.length) names.push("允许货型");
    if (names.length) missing.push(`${names.join("、")}（${el.typeElementId}）`);
  }
  if (missing.length) return `还差必填参数才能推演：${missing.join("；")}`;
  const links = conveyorLinks(draft.elements);
  const open = linear.filter((el) => !linearEndsLinked(el, links));
  if (open.length) return `输送还没接上：把端口对到邻段或月台后再推演（${open.map((el) => el.typeElementId).join("、")}）`;
  return "";
}

export function asBox(el: PoseEl): BoxEl {
  return {
    instanceId: el.instanceId,
    x: el.x,
    y: el.y,
    yawDeg: el.yawDeg,
    lengthM: el.lengthM,
    widthM: el.widthM,
  };
}

export function rebindAccess(draft: Draft): { draft: Draft; lost: string[] } {
  const aisle = aisleOf(draft);
  const lost: string[] = [];
  const elements = draft.elements.map((el) => {
    const spec = catalogItem(el.typeElementId);
    const access = projectAccess(el.x, el.y, aisle);
    if (spec?.accessRequired && !access) lost.push(el.instanceId);
    return {
      ...el,
      accessNodeId: access?.id ?? null,
      accessX: access?.x ?? null,
      accessY: access?.y ?? null,
    };
  });
  return { draft: { ...draft, elements }, lost };
}

export function verdictFor(draft: Draft, el: PoseEl, ignoreId: string | null) {
  const spec = catalogItem(el.typeElementId);
  const width = parseNum(draft.widthM);
  const height = parseNum(draft.heightM);
  return assessPlacement({
    x: el.x,
    y: el.y,
    lengthM: el.lengthM,
    widthM: el.widthM,
    yawDeg: el.yawDeg,
    accessRequired: Boolean(spec?.accessRequired),
    storageCopy: el.typeElementId === "ST-PAL-01" || el.typeElementId === "ST-FLOOR-01",
    facilityW: width,
    facilityH: height,
    aisle: aisleOf(draft),
    aisleWidthM: parseNum(draft.aisleWidthM),
    minClearWidthM: el.minClearWidthM,
    encroach: !AISLE_FACE.has(el.typeElementId),
    columns: columnsFor(draft),
    fireLane: width !== null && height !== null ? fireLaneInside(width, height) : null,
    others: draft.elements
      .filter((item) => item.instanceId !== ignoreId && item.instanceId !== el.instanceId)
      .map((item) => ({ ...asBox(item), fireZone: item.typeElementId === "AUX-FIRE-01" })),
  });
}

export function specOf(type: string): CatalogItem {
  const spec = catalogItem(type);
  if (!spec || !isPlaceable(type)) throw new Error(`不可放置 ${type}`);
  return spec;
}

export function emptyScenario(): ScenarioFields {
  return {
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
  };
}

export function testScenario(): ScenarioFields {
  return {
    fullPallet: true,
    breakBulk: false,
    piecePick: false,
    inbound: "",
    outbound: "4",
    shiftHours: "1",
    forklifts: "1",
    pickers: "0",
    travel: "1.2",
    emptySpeed: "1.5",
    pickSec: "10",
    shipSec: "5",
    windowSec: "20",
  };
}

export function parseNum(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function missingScenario(fields: ScenarioFields): string[] {
  const missing: string[] = [];
  const required: Array<[keyof ScenarioFields, string]> = [
    ["outbound", "日出量"],
    ["shiftHours", "班次窗"],
    ["forklifts", "叉车数量"],
    ["pickers", "拣货人数"],
    ["travel", "载货速度"],
    ["emptySpeed", "空驶速度"],
    ["pickSec", "取货时间"],
    ["shipSec", "发运时间"],
    ["windowSec", "到达窗口"],
  ];
  for (const [key, label] of required) {
    if (parseNum(String(fields[key])) === null) missing.push(label);
  }
  if (!fields.fullPallet && !fields.breakBulk && !fields.piecePick) missing.push("业务工况");
  return missing;
}

export function scenarioKey(fields: ScenarioFields): string {
  return JSON.stringify(fields);
}

function goods() {
  return {
    id: "gg-std-pallet",
    loadUnit: "pallet",
    dimensionsM: { length: 1.2, width: 1.0, height: 1.5 },
    grossWeightKg: 800,
    stackability: "stackable",
    allowedStorageTypes: ["ST-PAL-01"],
    quantityUnit: "pallet",
    evidence: EVIDENCE,
  };
}

function flow(flowKind: string, intent: string, source: string, quantity: number) {
  return {
    flowKind,
    intent,
    inputBasis: "explicit_quantity",
    quantity,
    unit: "pallet",
    source,
    downstream: null,
    conversionRef: null,
    parentFlowId: null,
  };
}

export function buildFacility(draft: Draft, id: string, revision: string) {
  const width = parseNum(draft.widthM);
  const height = parseNum(draft.heightM);
  if (width === null || height === null || width <= 0 || height <= 0) {
    throw new Error("场地宽和高未填写");
  }
  return {
    contractVersion: "0.3",
    id,
    revision,
    parentRef: null,
    coord: { origin: "facility_sw_corner", xAxis: "east", yAxis: "north", unit: "m" },
    boundary: {
      outer: [
        { x: 0, y: 0 },
        { x: width, y: 0 },
        { x: width, y: height },
        { x: 0, y: height },
        { x: 0, y: 0 },
      ],
    },
    obstacles: [],
    openings: [],
    reservedAreas: [],
    heightProfile: { kind: "uniform", heightM: 10 },
    evidence: EVIDENCE,
  };
}

function elementParams(el: PoseEl, elements: PoseEl[]): Record<string, unknown> {
  const params: Record<string, unknown> = {
    length_m: el.lengthM,
    width_m: el.widthM,
    height_m: el.heightM,
    orientation_deg: el.yawDeg,
    footprintW: el.lengthM,
    footprintD: el.widthM,
  };
  if (el.accessNodeId && el.accessX !== null && el.accessY !== null) {
    params.accessNodeId = el.accessNodeId;
    params.accessPoint = { x: el.accessX, y: el.accessY };
  }
  if (el.typeElementId === "ST-PAL-01") {
    const bays = el.bays ?? 1;
    const levels = el.levels ?? 1;
    params.bays = bays;
    params.levels = levels;
    params.palletsPerBay = el.palletsPerBay ?? 2;
    params.minClearWidthM = el.minClearWidthM ?? 3;
    params.geometry = {
      bay_w_m: el.lengthM / bays,
      bay_d_m: el.widthM,
      levels,
      level_height_m: el.heightM / levels,
      bays,
      aisle_w_m: el.minClearWidthM ?? 3,
      orientation_deg: el.yawDeg,
    };
  }
  if (el.typeElementId.startsWith("CV-")) {
    const speed = el.speedMpm === undefined ? 30 : el.speedMpm;
    if (speed !== null) params.speed_mpm = speed;
    if (isLinearConveyor(el.typeElementId)) {
      if (el.throughputUph != null) params.throughput_uph = el.throughputUph;
      else if (el.throughputUph === undefined) params.throughput_uph = 120;
      if (el.maxLoadKg != null) params.max_load_kg = el.maxLoadKg;
      else if (el.maxLoadKg === undefined) params.max_load_kg = 1500;
      params.direction = el.direction === null ? undefined : el.direction || "forward";
      if (el.direction === null) delete params.direction;
      params.allow_load_types = el.allowLoadTypes === null ? undefined : el.allowLoadTypes || ["pallet"];
      if (el.allowLoadTypes === null) delete params.allow_load_types;
      params.ports = [
        { id: "p_in", role: "in" },
        { id: "p_out", role: "out" },
      ];
      params.connector_ids = ["p_in", "p_out"];
      params.conveyorLinks = conveyorLinks(elements).filter(
        (link) => link.fromInstanceId === el.instanceId || link.toInstanceId === el.instanceId,
      );
    }
  }
  if (el.typeElementId === "ST-FLOOR-01") {
    params.levels = 1;
    params.bays = 1;
    params.palletsPerBay = el.palletsPerBay ?? 4;
    params.geometry = {
      length_m: el.lengthM,
      width_m: el.widthM,
      max_stack_h_m: el.heightM,
      orientation_deg: el.yawDeg,
    };
  }
  return params;
}

export function buildLayout(draft: Draft, id: string, revision: string, facilityRef: { id: string; revision: string }) {
  const fromX = parseNum(draft.aisleFromX);
  const toX = parseNum(draft.aisleToX);
  const y = parseNum(draft.aisleY);
  const width = parseNum(draft.aisleWidthM);
  const aisles =
    fromX !== null && toX !== null && y !== null && width !== null
      ? [
          {
            id: "aisle-main",
            centerline: [
              { x: fromX, y },
              { x: toX, y },
            ],
            widthM: width,
          },
        ]
      : [];
  return {
    contractVersion: "0.3",
    id,
    revision,
    facilityRef,
    parentRef: null,
    elements: draft.elements.map((el) => ({
      instanceId: el.instanceId,
      typeElementId: el.typeElementId,
      pose: { x: el.x, y: el.y, yawDeg: el.yawDeg },
      params: elementParams(el, draft.elements),
      assetDisposition: "new",
    })),
    aisles,
    locks: [],
    catalogVersion: "catalog-slice-manual",
  };
}

export function buildDemand(draft: Draft, fields: ScenarioFields) {
  const outbound = parseNum(fields.outbound);
  const inbound = fields.inbound.trim() === "" ? 0 : parseNum(fields.inbound);
  const windowSec = parseNum(fields.windowSec);
  if (outbound === null || windowSec === null || inbound === null) throw new Error("需求未填写完整");
  const flows = [];
  if (fields.fullPallet) flows.push(flow("full_pallet", "outbound", "storage", outbound));
  if (fields.breakBulk) flows.push(flow("break_bulk", "outbound", "storage", outbound));
  if (fields.piecePick) flows.push(flow("piece_pick", "outbound", "storage", outbound));
  if (fields.fullPallet && inbound > 0) flows.push(flow("full_pallet", "inbound", "external", inbound));
  const rack = draft.elements.find((el) => el.typeElementId === "ST-PAL-01");
  if (outbound > 0 && !rack) throw new Error("出库需要至少一座托盘货架");
  return {
    contractVersion: "0.3",
    id: "demand-workbench",
    revision: "pending",
    parentRef: null,
    goodsGroups: [goods()],
    inventoryTargets: [{ goodsGroupId: "gg-std-pallet", quantity: Math.max(outbound, 1), unit: "pallet" }],
    initialInventory:
      outbound > 0 && rack
        ? [
            {
              goodsGroupId: "gg-std-pallet",
              quantity: outbound,
              unit: "pallet",
              locationInstanceId: rack.instanceId,
            },
          ]
        : [],
    flows,
    arrivalProfile: {
      kind: "uniform",
      windowSec,
      unit: "pallet",
      paramsSource: "workbench-input",
    },
    serviceTargets: [],
    assumptions: ["数量和速度来自本次表单，不是界面演示公式"],
  };
}

export function buildOperating(fields: ScenarioFields) {
  const horizonH = parseNum(fields.shiftHours);
  const forklifts = parseNum(fields.forklifts);
  const pickers = parseNum(fields.pickers);
  const travel = parseNum(fields.travel);
  const emptySpeed = parseNum(fields.emptySpeed);
  const pickSec = parseNum(fields.pickSec);
  const shipSec = parseNum(fields.shipSec);
  if (
    horizonH === null ||
    forklifts === null ||
    pickers === null ||
    travel === null ||
    emptySpeed === null ||
    pickSec === null ||
    shipSec === null
  ) {
    throw new Error("工况未填写完整");
  }
  const pools = [
    {
      id: "pool-forklift",
      resourceType: "forklift",
      count: forklifts,
      capabilityRef: "cap-forklift-workbench",
      availableWindowSec: horizonH * 3600,
      homeInstanceIds: [],
    },
  ];
  if (pickers > 0) {
    pools.push({
      id: "pool-picker",
      resourceType: "picker",
      count: pickers,
      capabilityRef: "cap-picker-workbench",
      availableWindowSec: horizonH * 3600,
      homeInstanceIds: [],
    });
  }
  return {
    contractVersion: "0.3",
    id: "op-workbench",
    revision: "pending",
    parentRef: null,
    resourcePools: pools,
    serviceParameters: {
      travelSpeedMps: travel,
      emptySpeedMps: emptySpeed,
      processSec: { pick: pickSec, ship: shipSec },
      paramsSource: "workbench-input",
    },
    routingPolicy: { kind: "shortest_path" },
    shiftWindow: { startSec: 0, endSec: horizonH * 3600 },
  };
}

export function horizonSec(fields: ScenarioFields): number {
  const hours = parseNum(fields.shiftHours);
  if (hours === null) throw new Error("班次窗未填写");
  return hours * 3600;
}

export function nextInstance(elements: PoseEl[], type: PlaceableType): string {
  const prefix = instancePrefix(type);
  const taken = new Set(elements.map((el) => el.instanceId));
  let i = 1;
  let id = `${prefix}-${i}`;
  while (taken.has(id)) {
    i += 1;
    id = `${prefix}-${i}`;
  }
  return id;
}

export function elementFromDrop(
  elements: PoseEl[],
  type: PlaceableType,
  x: number,
  y: number,
  access: { id: string; x: number; y: number } | null,
): PoseEl {
  const spec = specOf(type);
  const bays = spec.defaultBays;
  const levels = spec.defaultLevels;
  const lengthM = spec.bayLengthM && bays ? spec.bayLengthM * bays : spec.lengthM;
  const heightM = spec.levelHeightM && levels ? spec.levelHeightM * levels : spec.heightM;
  return {
    instanceId: nextInstance(elements, type),
    typeElementId: type,
    x,
    y,
    yawDeg: spec.orientationDeg,
    lengthM,
    widthM: spec.widthM,
    heightM,
    accessNodeId: access?.id ?? null,
    accessX: access?.x ?? null,
    accessY: access?.y ?? null,
    bays,
    levels,
    palletsPerBay: spec.palletsPerBay,
    minClearWidthM: spec.minClearWidthM,
    ...conveyorDefaults(type),
  };
}

function conveyorDefaults(type: PlaceableType): Partial<PoseEl> {
  if (!type.startsWith("CV-")) return {};
  return {
    speedMpm: 30,
    throughputUph: isLinearConveyor(type) ? 120 : null,
    maxLoadKg: isLinearConveyor(type) ? 1500 : null,
    direction: isLinearConveyor(type) ? "forward" : null,
    allowLoadTypes: isLinearConveyor(type) ? ["pallet"] : null,
  };
}
