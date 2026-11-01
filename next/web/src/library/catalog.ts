export type CatalogGroup = "IN" | "ST" | "PK" | "CV" | "MH" | "OUT" | "AUX";

export type CatalogItem = {
  id: string;
  name: string;
  group: CatalogGroup;
  placeable: boolean;
  /** Along local +X at orientation 0°, meters. */
  lengthM: number;
  /** Along local +Y at orientation 0°, meters. */
  widthM: number;
  heightM: number;
  orientationDeg: number;
  /** Drop is refused unless a channel access node can be bound. */
  accessRequired: boolean;
  bayLengthM?: number;
  levelHeightM?: number;
  defaultBays?: number;
  defaultLevels?: number;
  palletsPerBay?: number;
  minClearWidthM?: number;
};

/** Formal library v0.1.6 ids, in panel order IN → ST → PK → CV → MH → OUT → AUX. */
export const LIBRARY_IDS = [
  "IN-DOCK-01",
  "IN-BUF-01",
  "IN-STAGE-01",
  "IN-QC-01",
  "IN-CHK-01",
  "IN-RTN-01",
  "IN-APT-01",
  "IN-ASN-01",
  "ST-PAL-01",
  "ST-BEAM-01",
  "ST-DRV-01",
  "ST-FLOW-01",
  "ST-MEZ-01",
  "ST-FLOOR-01",
  "ST-ASRS-01",
  "ST-COLD-01",
  "ST-HAZ-01",
  "ST-SLOW-01",
  "ST-OVF-01",
  "PK-FACE-01",
  "PK-STA-01",
  "PK-FULL-01",
  "PK-DEPAL-01",
  "PK-DEPAL-BUF-01",
  "PK-DEPAL-AUTO-01",
  "PK-EACH-01",
  "PK-BIN-FACE-01",
  "PK-PUT-EACH-01",
  "PK-TOTE-BUF-01",
  "PK-PTL-01",
  "PK-VOICE-01",
  "PK-WALL-01",
  "PK-PUT-01",
  "PK-CART-01",
  "PK-SLOT-01",
  "PK-EXC-01",
  "CV-STR-01",
  "CV-CURVE-01",
  "CV-VERT-01",
  "CV-MERGE-01",
  "CV-DIV-01",
  "CV-ROL-01",
  "CV-BELT-01",
  "CV-LOOP-01",
  "CV-CHUTE-01",
  "CV-BUF-01",
  "CV-INDUCT-EACH-01",
  "MH-FORK-01",
  "MH-HAND-01",
  "MH-AGV-01",
  "MH-CHG-01",
  "MH-WAIT-01",
  "MH-CRANE-01",
  "MH-HOIST-01",
  "MH-XFER-01",
  "MH-CART-01",
  "OUT-STG-01",
  "OUT-FULL-01",
  "OUT-PACK-01",
  "OUT-WGH-01",
  "OUT-DOCK-01",
  "OUT-BUF-01",
  "OUT-CARR-01",
  "OUT-PRT-01",
  "OUT-HOLD-01",
  "AUX-DESK-01",
  "AUX-REST-01",
  "AUX-FIRE-01",
  "AUX-EMPTY-PAL-01",
  "AUX-CHG-01",
  "AUX-MNT-01",
  "AUX-CONS-01",
  "AUX-GATE-01",
  "AUX-SCALE-01",
  "AUX-ZONE-01",
  "AUX-RAIL-01",
  "AUX-COL-01",
  "AUX-WALL-01",
] as const;

const LINEAR_CONVEYOR = new Set(["CV-STR-01", "CV-ROL-01", "CV-BELT-01"]);

const UNSIMULATED_EXACT = new Set([
  "MH-AGV-01",
  "MH-CHG-01",
  "MH-WAIT-01",
  "MH-CRANE-01",
  "MH-HOIST-01",
  "MH-XFER-01",
  "ST-ASRS-01",
  "PK-DEPAL-AUTO-01",
]);

export function isLinearConveyor(typeId: string): boolean {
  return LINEAR_CONVEYOR.has(typeId);
}

export function isUnsimulated(typeId: string): boolean {
  if (LINEAR_CONVEYOR.has(typeId)) return false;
  return typeId.startsWith("CV-") || UNSIMULATED_EXACT.has(typeId);
}

export function unsimulatedMessage(typeIds: string[]): string {
  const shown: string[] = [];
  for (const typeId of typeIds) {
    if (typeId && isUnsimulated(typeId) && !shown.includes(typeId)) shown.push(typeId);
  }
  if (!shown.length) return "";
  return `本切片暂不仿真该类：${shown.join("、")}。可以保存落位，但不会为这些类型编造四卡。`;
}

type Seed = {
  id: string;
  name: string;
  lengthM: number;
  widthM: number;
  heightM: number;
  orientationDeg?: number;
  bayLengthM?: number;
  levelHeightM?: number;
  defaultBays?: number;
  defaultLevels?: number;
  palletsPerBay?: number;
  minClearWidthM?: number;
};

const SEEDS: Seed[] = [
  { id: "IN-DOCK-01", name: "入库月台", lengthM: 3, widthM: 4, heightM: 1.2 },
  { id: "IN-BUF-01", name: "收货缓冲区", lengthM: 6, widthM: 3, heightM: 1.8 },
  { id: "IN-STAGE-01", name: "到货暂存区", lengthM: 6, widthM: 4, heightM: 1.8 },
  { id: "IN-QC-01", name: "质检工位", lengthM: 2.4, widthM: 1.6, heightM: 1.1 },
  { id: "IN-CHK-01", name: "收货复核台", lengthM: 2.4, widthM: 1.4, heightM: 1.1 },
  { id: "IN-RTN-01", name: "退货收货口", lengthM: 3, widthM: 4, heightM: 1.2 },
  { id: "IN-APT-01", name: "预约登记点", lengthM: 2, widthM: 1.5, heightM: 1.1 },
  { id: "IN-ASN-01", name: "ASN核对点", lengthM: 2, widthM: 1.5, heightM: 1.1 },
  {
    id: "ST-PAL-01",
    name: "托盘货架",
    lengthM: 2.7,
    widthM: 1.2,
    heightM: 6,
    bayLengthM: 2.7,
    levelHeightM: 1.5,
    defaultBays: 1,
    defaultLevels: 4,
    palletsPerBay: 2,
    minClearWidthM: 3,
  },
  { id: "ST-BEAM-01", name: "重型横梁货架", lengthM: 2.7, widthM: 1.2, heightM: 6 },
  { id: "ST-DRV-01", name: "驶入式货架", lengthM: 4.8, widthM: 2.4, heightM: 6 },
  { id: "ST-FLOW-01", name: "流利式货架", lengthM: 4, widthM: 1.2, heightM: 2.2 },
  { id: "ST-MEZ-01", name: "阁楼货架", lengthM: 6, widthM: 3, heightM: 4 },
  {
    id: "ST-FLOOR-01",
    name: "地堆区",
    lengthM: 4.8,
    widthM: 2.4,
    heightM: 1.5,
    defaultLevels: 1,
    defaultBays: 1,
    palletsPerBay: 4,
  },
  { id: "ST-ASRS-01", name: "高位立体库位", lengthM: 2.7, widthM: 1.4, heightM: 8 },
  { id: "ST-COLD-01", name: "冷库隔间", lengthM: 6, widthM: 4, heightM: 4 },
  { id: "ST-HAZ-01", name: "危险品专区", lengthM: 4, widthM: 3, heightM: 3 },
  { id: "ST-SLOW-01", name: "呆滞品隔离区", lengthM: 4.8, widthM: 2.4, heightM: 1.5 },
  { id: "ST-OVF-01", name: "临时溢放区", lengthM: 4.8, widthM: 2.4, heightM: 1.5 },
  { id: "PK-FACE-01", name: "拣选面", lengthM: 2.7, widthM: 1.2, heightM: 2 },
  { id: "PK-STA-01", name: "拣选工位", lengthM: 2, widthM: 1.5, heightM: 1.8 },
  { id: "PK-FULL-01", name: "整托拣选位", lengthM: 2.7, widthM: 1.5, heightM: 1.5 },
  { id: "PK-DEPAL-01", name: "拆托工位", lengthM: 3.2, widthM: 2, heightM: 1.6 },
  { id: "PK-DEPAL-BUF-01", name: "拆托缓冲区", lengthM: 4, widthM: 2.4, heightM: 1.5 },
  { id: "PK-DEPAL-AUTO-01", name: "半自动拆托机位", lengthM: 3.6, widthM: 2.2, heightM: 2.2 },
  { id: "PK-EACH-01", name: "小件拣选面", lengthM: 2.4, widthM: 0.8, heightM: 2 },
  { id: "PK-BIN-FACE-01", name: "料箱货架拣选面", lengthM: 3.6, widthM: 1, heightM: 2.2 },
  { id: "PK-PUT-EACH-01", name: "播种格口", lengthM: 4.2, widthM: 1, heightM: 2.2 },
  { id: "PK-TOTE-BUF-01", name: "料箱周转箱暂存", lengthM: 2.4, widthM: 1.2, heightM: 1.5 },
  { id: "PK-PTL-01", name: "电子标签拣选区", lengthM: 3, widthM: 0.8, heightM: 2 },
  { id: "PK-VOICE-01", name: "语音拣选通道", lengthM: 6, widthM: 1.2, heightM: 0.2 },
  { id: "PK-WALL-01", name: "播种墙", lengthM: 4.2, widthM: 0.6, heightM: 2.2 },
  { id: "PK-PUT-01", name: "分播台", lengthM: 2.2, widthM: 1.4, heightM: 1.1 },
  { id: "PK-CART-01", name: "拣选小车停靠位", lengthM: 1.6, widthM: 1.2, heightM: 0.3 },
  { id: "PK-SLOT-01", name: "订单暂存格", lengthM: 2.4, widthM: 0.6, heightM: 1.8 },
  { id: "PK-EXC-01", name: "异常拣选复核台", lengthM: 2.2, widthM: 1.4, heightM: 1.1 },
  { id: "CV-STR-01", name: "直线输送机", lengthM: 6, widthM: 0.8, heightM: 0.9 },
  { id: "CV-CURVE-01", name: "转弯输送机", lengthM: 2, widthM: 2, heightM: 0.9 },
  { id: "CV-VERT-01", name: "升降机", lengthM: 1.6, widthM: 1.6, heightM: 3 },
  { id: "CV-MERGE-01", name: "合流点", lengthM: 2.4, widthM: 2.4, heightM: 0.9 },
  { id: "CV-DIV-01", name: "分流点", lengthM: 2.4, widthM: 2.4, heightM: 0.9 },
  { id: "CV-ROL-01", name: "滚筒线", lengthM: 6, widthM: 0.8, heightM: 0.9 },
  { id: "CV-BELT-01", name: "皮带线", lengthM: 6, widthM: 0.8, heightM: 0.9 },
  { id: "CV-LOOP-01", name: "环形分拣环", lengthM: 6, widthM: 2, heightM: 0.9 },
  { id: "CV-CHUTE-01", name: "滑槽", lengthM: 3, widthM: 1.2, heightM: 1.5 },
  { id: "CV-BUF-01", name: "缓存输送段", lengthM: 4, widthM: 0.8, heightM: 0.9 },
  { id: "CV-INDUCT-EACH-01", name: "小件分拣导入点", lengthM: 2.2, widthM: 1.4, heightM: 1.2 },
  { id: "MH-FORK-01", name: "叉车作业区", lengthM: 4, widthM: 2.2, heightM: 0.25 },
  { id: "MH-HAND-01", name: "手动托盘车通道", lengthM: 6, widthM: 1.2, heightM: 0.2 },
  { id: "MH-AGV-01", name: "AGV行驶路径段", lengthM: 6, widthM: 1.5, heightM: 0.2 },
  { id: "MH-CHG-01", name: "AGV充电站", lengthM: 1.6, widthM: 1.2, heightM: 1.5 },
  { id: "MH-WAIT-01", name: "AGV待命点", lengthM: 2, widthM: 2, heightM: 0.2 },
  { id: "MH-CRANE-01", name: "堆垛机巷道", lengthM: 8, widthM: 1.6, heightM: 6 },
  { id: "MH-HOIST-01", name: "提升机井道", lengthM: 2, widthM: 2, heightM: 6 },
  { id: "MH-XFER-01", name: "跨层移交点", lengthM: 2.4, widthM: 2, heightM: 1.5 },
  { id: "MH-CART-01", name: "人工推车通道", lengthM: 6, widthM: 1.2, heightM: 0.2 },
  { id: "OUT-STG-01", name: "集货位", lengthM: 4.8, widthM: 2.4, heightM: 1.5 },
  { id: "OUT-FULL-01", name: "整托集货位", lengthM: 4.8, widthM: 1.3, heightM: 1.5 },
  { id: "OUT-PACK-01", name: "复核打包台", lengthM: 2.4, widthM: 1.4, heightM: 1.1 },
  { id: "OUT-WGH-01", name: "称重扫描点", lengthM: 1.6, widthM: 1.2, heightM: 1.5 },
  { id: "OUT-DOCK-01", name: "出库月台", lengthM: 3, widthM: 4, heightM: 1.2, orientationDeg: 180 },
  { id: "OUT-BUF-01", name: "装车缓冲区", lengthM: 6, widthM: 3, heightM: 1.8 },
  { id: "OUT-CARR-01", name: "承运商分区格口", lengthM: 4.2, widthM: 1, heightM: 2 },
  { id: "OUT-PRT-01", name: "单据打印点", lengthM: 1.2, widthM: 0.8, heightM: 1.2 },
  { id: "OUT-HOLD-01", name: "发运暂存区", lengthM: 6, widthM: 3, heightM: 1.8 },
  { id: "AUX-DESK-01", name: "办公调度台", lengthM: 2, widthM: 1.2, heightM: 1.1 },
  { id: "AUX-REST-01", name: "休息区", lengthM: 4, widthM: 3, heightM: 2.4 },
  { id: "AUX-FIRE-01", name: "消防通道", lengthM: 6, widthM: 1.5, heightM: 0.15 },
  { id: "AUX-EMPTY-PAL-01", name: "空托盘回收位", lengthM: 2.4, widthM: 1.2, heightM: 1.5 },
  { id: "AUX-CHG-01", name: "叉车充电桩", lengthM: 1.2, widthM: 0.8, heightM: 1.5 },
  { id: "AUX-MNT-01", name: "维修间", lengthM: 4, widthM: 3, heightM: 3 },
  { id: "AUX-CONS-01", name: "耗材仓", lengthM: 3, widthM: 2, heightM: 2.4 },
  { id: "AUX-GATE-01", name: "道闸门禁", lengthM: 3, widthM: 0.4, heightM: 2 },
  { id: "AUX-SCALE-01", name: "地磅", lengthM: 8, widthM: 3, heightM: 0.3 },
  { id: "AUX-ZONE-01", name: "照明温控分区", lengthM: 6, widthM: 4, heightM: 0.1 },
  { id: "AUX-RAIL-01", name: "安全护栏", lengthM: 4, widthM: 0.15, heightM: 1.1 },
  { id: "AUX-COL-01", name: "立柱", lengthM: 0.6, widthM: 0.6, heightM: 4 },
  { id: "AUX-WALL-01", name: "墙体与门洞", lengthM: 8, widthM: 0.3, heightM: 3.2 },
];

function groupOf(id: string): CatalogGroup {
  return id.slice(0, id.indexOf("-")) as CatalogGroup;
}

export const catalog: CatalogItem[] = SEEDS.map((seed) => ({
  id: seed.id,
  name: seed.name,
  group: groupOf(seed.id),
  placeable: true,
  lengthM: seed.lengthM,
  widthM: seed.widthM,
  heightM: seed.heightM,
  orientationDeg: seed.orientationDeg ?? 0,
  accessRequired: true,
  bayLengthM: seed.bayLengthM,
  levelHeightM: seed.levelHeightM,
  defaultBays: seed.defaultBays,
  defaultLevels: seed.defaultLevels,
  palletsPerBay: seed.palletsPerBay,
  minClearWidthM: seed.minClearWidthM,
}));

export const PLACEABLE_IDS = catalog.filter((item) => item.placeable).map((item) => item.id);

export const SLICE11_IDS = [
  "IN-DOCK-01",
  "ST-PAL-01",
  "ST-FLOOR-01",
  "PK-DEPAL-01",
  "PK-PUT-EACH-01",
  "OUT-PACK-01",
  "OUT-DOCK-01",
  "MH-HAND-01",
  "MH-FORK-01",
  "AUX-FIRE-01",
  "AUX-WALL-01",
];

export const groupLabels: Array<[CatalogGroup, string]> = [
  ["IN", "入库"],
  ["ST", "存储"],
  ["PK", "拣选"],
  ["CV", "输送"],
  ["MH", "搬运"],
  ["OUT", "出库"],
  ["AUX", "辅助"],
];

export function catalogItem(id: string): CatalogItem | undefined {
  return catalog.find((item) => item.id === id);
}

export function isPlaceable(id: string): boolean {
  return Boolean(catalogItem(id)?.placeable);
}

export function instancePrefix(typeId: string): string {
  return typeId.toLowerCase();
}
