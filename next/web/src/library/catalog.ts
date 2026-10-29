export type CatalogGroup = "storage" | "dock" | "station" | "structure";

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

/**
 * Slice-11 placeables use equip length_m / width_m / height_m / orientation_deg.
 * Grey rows are the out-of-slice families only (conveyor, AGV, AS/RS).
 */
export const catalog: CatalogItem[] = [
  {
    id: "ST-PAL-01",
    name: "托盘货架",
    group: "storage",
    placeable: true,
    lengthM: 2.7,
    widthM: 1.2,
    heightM: 6,
    orientationDeg: 0,
    accessRequired: true,
    bayLengthM: 2.7,
    levelHeightM: 1.5,
    defaultBays: 1,
    defaultLevels: 4,
    palletsPerBay: 2,
    minClearWidthM: 3,
  },
  {
    id: "ST-FLOOR-01",
    name: "地堆区",
    group: "storage",
    placeable: true,
    lengthM: 4.8,
    widthM: 2.4,
    heightM: 1.5,
    orientationDeg: 0,
    accessRequired: true,
    defaultLevels: 1,
    defaultBays: 1,
    palletsPerBay: 4,
  },
  {
    id: "IN-DOCK-01",
    name: "入库月台",
    group: "dock",
    placeable: true,
    lengthM: 3,
    widthM: 4,
    heightM: 1.2,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "OUT-DOCK-01",
    name: "出库月台",
    group: "dock",
    placeable: true,
    lengthM: 3,
    widthM: 4,
    heightM: 1.2,
    orientationDeg: 180,
    accessRequired: true,
  },
  {
    id: "PK-DEPAL-01",
    name: "拆托工位",
    group: "station",
    placeable: true,
    lengthM: 3.2,
    widthM: 2,
    heightM: 1.6,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "PK-PUT-EACH-01",
    name: "播种格口",
    group: "station",
    placeable: true,
    lengthM: 4.2,
    widthM: 1,
    heightM: 2.2,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "OUT-PACK-01",
    name: "复核打包台",
    group: "station",
    placeable: true,
    lengthM: 2.4,
    widthM: 1.4,
    heightM: 1.1,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "MH-HAND-01",
    name: "手动托盘车通道",
    group: "structure",
    placeable: true,
    lengthM: 6,
    widthM: 1.2,
    heightM: 0.2,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "MH-FORK-01",
    name: "叉车作业区",
    group: "structure",
    placeable: true,
    lengthM: 4,
    widthM: 2.2,
    heightM: 0.25,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "AUX-FIRE-01",
    name: "消防通道",
    group: "structure",
    placeable: true,
    lengthM: 6,
    widthM: 1.5,
    heightM: 0.15,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "AUX-WALL-01",
    name: "墙体与门洞",
    group: "structure",
    placeable: true,
    lengthM: 8,
    widthM: 0.3,
    heightM: 3.2,
    orientationDeg: 0,
    accessRequired: true,
  },
  {
    id: "CV-BELT-01",
    name: "输送线段",
    group: "station",
    placeable: false,
    lengthM: 6,
    widthM: 0.8,
    heightM: 0.9,
    orientationDeg: 0,
    accessRequired: false,
  },
  {
    id: "AGV-AMR-01",
    name: "潜伏式 AGV",
    group: "structure",
    placeable: false,
    lengthM: 1.2,
    widthM: 0.8,
    heightM: 0.35,
    orientationDeg: 0,
    accessRequired: false,
  },
  {
    id: "ASRS-CRANE-01",
    name: "立体库货架",
    group: "storage",
    placeable: false,
    lengthM: 12,
    widthM: 1.4,
    heightM: 12,
    orientationDeg: 0,
    accessRequired: false,
  },
];

export const PLACEABLE_IDS = catalog.filter((item) => item.placeable).map((item) => item.id);

export const groupLabels: Array<[CatalogGroup, string]> = [
  ["storage", "存储设备"],
  ["dock", "月台设施"],
  ["station", "作业工位"],
  ["structure", "通道与结构"],
];

export function catalogItem(id: string): CatalogItem | undefined {
  return catalog.find((item) => item.id === id);
}

export function isPlaceable(id: string): boolean {
  return Boolean(catalogItem(id)?.placeable);
}
