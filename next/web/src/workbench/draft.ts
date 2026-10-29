/** Shared document builders. Blank and rectangle starts both use these functions. */

export type PlaceableType = "ST-PAL-01" | "IN-DOCK-01" | "OUT-DOCK-01";

export type PoseEl = {
  instanceId: string;
  typeElementId: PlaceableType;
  x: number;
  y: number;
  yawDeg: number;
};

export type Draft = {
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

export function draftFor(mode: "blank" | "rectangle"): Draft {
  if (mode === "rectangle") {
    return {
      widthM: "40",
      heightM: "24",
      aisleWidthM: "3.5",
      aisleFromX: "2",
      aisleToX: "38",
      aisleY: "12",
      elements: [],
    };
  }
  return {
    widthM: "",
    heightM: "",
    aisleWidthM: "",
    aisleFromX: "",
    aisleToX: "",
    aisleY: "",
    elements: [],
  };
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
      params:
        el.typeElementId === "ST-PAL-01"
          ? { levels: 4, bays: 1, palletsPerBay: 2, minClearWidthM: 3 }
          : {},
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
  const prefix = type === "ST-PAL-01" ? "rack" : type === "IN-DOCK-01" ? "dock-recv" : "dock-ship";
  const taken = new Set(elements.map((el) => el.instanceId));
  let i = 1;
  let id = `${prefix}-${i}`;
  while (taken.has(id)) {
    i += 1;
    id = `${prefix}-${i}`;
  }
  return id;
}
