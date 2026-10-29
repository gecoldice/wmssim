/** 与 simapp_derive.DEFAULT_FOOTPRINTS 一致的盒子代理。不是 GLB，也不含演示 KPI。 */

export type LibraryItem = {
  typeElementId: string;
  name: string;
  category: "货架/地堆" | "月台/工位" | "搬运/辅助";
  footprintW: number;
  footprintD: number;
  params: Record<string, number>;
};

export const LIBRARY: LibraryItem[] = [
  {
    typeElementId: "ST-PAL-01",
    name: "标准托盘货架",
    category: "货架/地堆",
    footprintW: 2.7,
    footprintD: 1.2,
    params: { levels: 4, bays: 1, palletsPerBay: 2, minClearWidthM: 3 },
  },
  {
    typeElementId: "IN-DOCK-01",
    name: "收货月台",
    category: "月台/工位",
    footprintW: 3,
    footprintD: 4,
    params: {},
  },
  {
    typeElementId: "OUT-DOCK-01",
    name: "发货月台",
    category: "月台/工位",
    footprintW: 3,
    footprintD: 4,
    params: {},
  },
  {
    typeElementId: "MH-HAND-01",
    name: "平衡重叉车",
    category: "搬运/辅助",
    footprintW: 1.2,
    footprintD: 2,
    params: {},
  },
];

export const CATEGORIES = ["货架/地堆", "月台/工位", "搬运/辅助"] as const;

export function libraryItem(typeElementId: string): LibraryItem | undefined {
  return LIBRARY.find((item) => item.typeElementId === typeElementId);
}

export function defaultParams(item: LibraryItem): Record<string, number> {
  return {
    ...item.params,
    footprintW: item.footprintW,
    footprintD: item.footprintD,
  };
}
