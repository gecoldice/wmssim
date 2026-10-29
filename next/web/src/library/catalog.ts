export type CatalogGroup = "storage" | "dock" | "station" | "structure";

export type CatalogItem = {
  id: string;
  name: string;
  group: CatalogGroup;
  placeable: boolean;
  w: number;
  d: number;
};

/** Footprints in meters for the three types this slice can place. */
export const catalog: CatalogItem[] = [
  { id: "ST-PAL-01", name: "托盘货架", group: "storage", placeable: true, w: 2.7, d: 1.2 },
  { id: "ST-FLOOR-01", name: "地堆区", group: "storage", placeable: false, w: 2.7, d: 1.2 },
  { id: "IN-DOCK-01", name: "入库月台", group: "dock", placeable: true, w: 3, d: 4 },
  { id: "OUT-DOCK-01", name: "出库月台", group: "dock", placeable: true, w: 3, d: 4 },
  { id: "PK-STA-01", name: "拣选工位", group: "station", placeable: false, w: 2, d: 2 },
  { id: "PK-DEPAL-01", name: "拆托工位", group: "station", placeable: false, w: 2, d: 2 },
  { id: "PK-PUT-EACH-01", name: "播种格口", group: "station", placeable: false, w: 2, d: 2 },
  { id: "OUT-PACK-01", name: "复核打包台", group: "station", placeable: false, w: 2, d: 2 },
  { id: "MH-HAND-01", name: "手动托盘车通道", group: "structure", placeable: false, w: 2, d: 1 },
  { id: "MH-FORK-01", name: "叉车作业区", group: "structure", placeable: false, w: 2, d: 2 },
  { id: "AUX-FIRE-01", name: "消防通道", group: "structure", placeable: false, w: 2, d: 1 },
  { id: "AUX-WALL-01", name: "墙体与门洞", group: "structure", placeable: false, w: 2, d: 1 },
];

export const groupLabels: Array<[CatalogGroup, string]> = [
  ["storage", "存储设备"],
  ["dock", "月台设施"],
  ["station", "作业工位"],
  ["structure", "通道与结构"],
];

export function catalogItem(id: string): CatalogItem | undefined {
  return catalog.find((item) => item.id === id);
}
