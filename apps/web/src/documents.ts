import { defaultParams, libraryItem } from "./library";

export type PlacedElement = {
  instanceId: string;
  typeElementId: string;
  x: number;
  y: number;
  yawDeg: number;
  params: Record<string, number>;
  assetDisposition: "new" | "existing" | "relocated" | "removed";
};

const STAMP = "2026-10-29T08:00:00+08:00";

function evidence(sourceKind: string, sourceRef: string) {
  return {
    sourceKind,
    sourceRef,
    confirmationStatus: "confirmed",
    updatedAt: STAMP,
  };
}

export function buildFacility(widthM: number, depthM: number, revision: string) {
  const mid = depthM / 2;
  const door = Math.min(2, Math.max(0.5, depthM / 6));
  return {
    contractVersion: "0.3",
    id: "facility-workbench",
    revision,
    parentRef: null,
    coord: { origin: "facility_sw_corner", xAxis: "east", yAxis: "north", unit: "m" },
    boundary: {
      outer: [
        { x: 0, y: 0 },
        { x: widthM, y: 0 },
        { x: widthM, y: depthM },
        { x: 0, y: depthM },
        { x: 0, y: 0 },
      ],
    },
    obstacles: [],
    openings: [
      {
        id: "door-recv",
        segment: [
          { x: 0, y: mid - door },
          { x: 0, y: mid + door },
        ],
        widthM: door * 2,
        heightM: 4.5,
        role: "recv",
        approachPolygon: null,
        evidence: evidence("manual", "workbench"),
      },
      {
        id: "door-ship",
        segment: [
          { x: widthM, y: mid - door },
          { x: widthM, y: mid + door },
        ],
        widthM: door * 2,
        heightM: 4.5,
        role: "ship",
        approachPolygon: null,
        evidence: evidence("manual", "workbench"),
      },
    ],
    reservedAreas: [],
    heightProfile: { kind: "uniform", heightM: 10 },
    evidence: evidence("manual", "workbench"),
  };
}

export function buildLayout(args: {
  layoutId: string;
  revision: string;
  facilityRevision: string;
  elements: PlacedElement[];
  widthM: number;
  depthM: number;
  aisleWidthM: number;
  aisleYM: number;
}) {
  const x0 = Math.min(2, args.widthM / 4);
  const x1 = Math.max(args.widthM - 2, x0);
  return {
    contractVersion: "0.3",
    id: args.layoutId,
    revision: args.revision,
    facilityRef: { id: "facility-workbench", revision: args.facilityRevision },
    parentRef: null,
    elements: args.elements.map((el) => ({
      instanceId: el.instanceId,
      typeElementId: el.typeElementId,
      pose: { x: el.x, y: el.y, yawDeg: el.yawDeg },
      params: el.params,
      assetDisposition: el.assetDisposition,
    })),
    aisles: [
      {
        id: "aisle-main",
        centerline: [
          { x: x0, y: args.aisleYM },
          { x: x1, y: args.aisleYM },
        ],
        widthM: args.aisleWidthM,
      },
    ],
    locks: [],
    catalogVersion: "catalog-mvp@c-r1",
  };
}

export function buildSimDemand(quantity: number, revision: string, locationInstanceId: string) {
  return {
    contractVersion: "0.3",
    id: "demand-workbench",
    revision,
    parentRef: null,
    goodsGroups: [
      {
        id: "gg-std-pallet",
        loadUnit: "pallet",
        dimensionsM: { length: 1.2, width: 1.0, height: 1.5 },
        grossWeightKg: 800,
        stackability: "stackable",
        allowedStorageTypes: ["ST-PAL-01"],
        quantityUnit: "pallet",
        evidence: evidence("manual", "workbench"),
      },
    ],
    inventoryTargets: [{ goodsGroupId: "gg-std-pallet", quantity, unit: "pallet" }],
    initialInventory: [
      {
        goodsGroupId: "gg-std-pallet",
        quantity,
        unit: "pallet",
        locationInstanceId,
      },
    ],
    flows: [
      {
        flowKind: "full_pallet",
        intent: "outbound",
        inputBasis: "explicit_quantity",
        quantity,
        unit: "pallet",
        source: "storage",
        downstream: null,
        conversionRef: null,
        parentFlowId: null,
      },
    ],
    arrivalProfile: {
      kind: "uniform",
      windowSec: 600,
      unit: "pallet",
      paramsSource: "workbench-input",
    },
    serviceTargets: [],
    assumptions: ["工作台输入的出库量，不是计算结果"],
    totalDemand: { quantity, unit: "pallet" },
  };
}

export function buildPlanningDemand() {
  return {
    contractVersion: "0.3",
    id: "demand-plan-ui",
    revision: "d-plan-1",
    parentRef: null,
    goodsGroups: [
      {
        id: "gg-std-pallet",
        loadUnit: "pallet",
        dimensionsM: { length: 1.2, width: 1.0, height: 1.5 },
        grossWeightKg: 800,
        stackability: "stackable",
        allowedStorageTypes: ["ST-PAL-01", "ST-FLOOR-01"],
        quantityUnit: "pallet",
        evidence: evidence("manual", "workbench-plan"),
      },
    ],
    inventoryTargets: [{ goodsGroupId: "gg-std-pallet", quantity: 48, unit: "pallet" }],
    initialInventory: [],
    flows: [],
    arrivalProfile: {
      kind: "uniform",
      windowSec: 28800,
      unit: "pallet",
      paramsSource: "workbench-plan",
    },
    serviceTargets: [],
    assumptions: ["规划输入：库存目标 48 托。quick 评估不是运营效率。"],
    totalDemand: null,
  };
}

export function buildOperating(forkliftCount: number, revision: string) {
  return {
    contractVersion: "0.3",
    id: "op-workbench",
    revision,
    parentRef: null,
    resourcePools: [
      {
        id: "pool-forklift",
        resourceType: "forklift",
        count: forkliftCount,
        capabilityRef: "cap-forklift-std",
        availableWindowSec: 3600,
        homeInstanceIds: [],
        skillTags: ["certified"],
      },
    ],
    serviceParameters: {
      travelSpeedMps: 1.2,
      emptySpeedMps: 1.5,
      processSec: { pick: 10, ship: 5, full_pallet: 10 },
    },
    routingPolicy: { kind: "shortest_path" },
    shiftWindow: { startSec: 0, endSec: 3600 },
    faults: [{ faultType: "edge_block", enabled: true, startTime: 100, duration: 60 }],
  };
}

export function templateElements(): PlacedElement[] {
  const rack = libraryItem("ST-PAL-01");
  const recv = libraryItem("IN-DOCK-01");
  const ship = libraryItem("OUT-DOCK-01");
  if (!rack || !recv || !ship) return [];
  return [
    {
      instanceId: "rack-001",
      typeElementId: rack.typeElementId,
      x: 12,
      y: 14,
      yawDeg: 0,
      params: defaultParams(rack),
      assetDisposition: "new",
    },
    {
      instanceId: "dock-recv",
      typeElementId: recv.typeElementId,
      x: 1.5,
      y: 12,
      yawDeg: 0,
      params: defaultParams(recv),
      assetDisposition: "new",
    },
    {
      instanceId: "dock-ship",
      typeElementId: ship.typeElementId,
      x: 38.5,
      y: 12,
      yawDeg: 180,
      params: defaultParams(ship),
      assetDisposition: "new",
    },
  ];
}

/** 演示价目，只作为成本接口的输入。demoOnly 必须保持 true。 */
export function demoPriceBook() {
  return {
    contractVersion: "0.3",
    id: "pb-workbench",
    revision: "pb-r1",
    parentRef: null,
    currency: "CNY",
    demoOnly: true,
    items: [
      {
        skuKey: "ST-PAL-01",
        unitPrice: 12000,
        unit: "ea",
        status: "available",
        source: "demo-catalog",
        asOf: "2026-10-01",
        taxInclusive: true,
        specNote: "标准托盘货架段",
      },
      {
        skuKey: "IN-DOCK-01",
        unitPrice: 8000,
        unit: "ea",
        status: "available",
        source: "demo-catalog",
        asOf: "2026-10-01",
        taxInclusive: true,
        specNote: null,
      },
      {
        skuKey: "OUT-DOCK-01",
        unitPrice: 8000,
        unit: "ea",
        status: "available",
        source: "demo-catalog",
        asOf: "2026-10-01",
        taxInclusive: true,
        specNote: null,
      },
      {
        skuKey: "resource:forklift",
        unitPrice: 50000,
        unit: "ea",
        status: "available",
        source: "demo-opex",
        asOf: "2026-10-01",
        taxInclusive: true,
        specNote: "年租当量（demo）",
      },
      {
        skuKey: "resource:operator",
        unitPrice: 80000,
        unit: "ea",
        status: "available",
        source: "demo-opex",
        asOf: "2026-10-01",
        taxInclusive: true,
        specNote: "年人力（demo）",
      },
      {
        skuKey: "relocate:ST-PAL-01",
        unitPrice: 1500,
        unit: "ea",
        status: "available",
        source: "demo-move",
        asOf: "2026-10-01",
        taxInclusive: true,
        specNote: "货架搬移",
      },
    ],
  };
}

export function demoCostBasis() {
  return {
    contractVersion: "0.3",
    id: "cb-workbench",
    revision: "cb-r1",
    parentRef: null,
    currency: "CNY",
    horizonYears: 5,
    includeInstallFee: true,
    includeRelocateFee: true,
    purchaseIncludesInstall: false,
    feeSchedule: [
      { kind: "install", rate: 1000, unit: "ea" },
      { kind: "relocate", rate: 1500, unit: "ea" },
    ],
    fxRate: null,
    notes: "工作台演示口径，不是供应商报价。购置与安装分列。",
  };
}

export function demoScoreProfile() {
  return {
    contractVersion: "0.3",
    id: "sp-workbench",
    revision: "sp-r1",
    parentRef: null,
    locked: true,
    axes: {
      storage: { direction: "higher_better", bad: 10, good: 80, unit: "pallet_slots" },
      efficiency: { direction: "lower_better", bad: 600, good: 60, unit: "s" },
      investment: { direction: "lower_better", bad: 200000, good: 20000, unit: "CNY" },
    },
  };
}

export function elementsFromDocument(raw: unknown): PlacedElement[] {
  if (!raw || typeof raw !== "object") return [];
  const elements = (raw as { elements?: unknown }).elements;
  if (!Array.isArray(elements)) return [];
  const placed: PlacedElement[] = [];
  for (const item of elements) {
    if (!item || typeof item !== "object") continue;
    const row = item as {
      instanceId?: string;
      typeElementId?: string;
      pose?: { x?: number; y?: number; yawDeg?: number };
      params?: Record<string, unknown>;
      assetDisposition?: PlacedElement["assetDisposition"];
    };
    if (!row.instanceId || !row.typeElementId) continue;
    const params: Record<string, number> = {};
    for (const [key, value] of Object.entries(row.params ?? {})) {
      if (typeof value === "number") params[key] = value;
    }
    const known = libraryItem(row.typeElementId);
    if (params.footprintW === undefined && known) params.footprintW = known.footprintW;
    if (params.footprintD === undefined && known) params.footprintD = known.footprintD;
    placed.push({
      instanceId: row.instanceId,
      typeElementId: row.typeElementId,
      x: Number(row.pose?.x ?? 0),
      y: Number(row.pose?.y ?? 0),
      yawDeg: Number(row.pose?.yawDeg ?? 0),
      params,
      assetDisposition: row.assetDisposition ?? "new",
    });
  }
  return placed;
}
