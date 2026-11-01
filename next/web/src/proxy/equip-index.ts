import auxFire from "./equip/AUX-FIRE-01.json";
import auxWall from "./equip/AUX-WALL-01.json";
import inBuf from "./equip/IN-BUF-01.json";
import inDock from "./equip/IN-DOCK-01.json";
import mhFork from "./equip/MH-FORK-01.json";
import mhHand from "./equip/MH-HAND-01.json";
import outBuf from "./equip/OUT-BUF-01.json";
import outDock from "./equip/OUT-DOCK-01.json";
import outFull from "./equip/OUT-FULL-01.json";
import outPack from "./equip/OUT-PACK-01.json";
import pkDepal from "./equip/PK-DEPAL-01.json";
import pkPut from "./equip/PK-PUT-EACH-01.json";
import pkSta from "./equip/PK-STA-01.json";
import stFloor from "./equip/ST-FLOOR-01.json";
import stPal from "./equip/ST-PAL-01.json";

export type Equip = {
  element_id: string;
  element_type?: string;
  glb?: string;
  lod?: { lod1?: string };
  visual?: { proxy?: string };
  colliders?: unknown[];
  ports?: Array<{ id: string; x_m?: number; y_m?: number; z_m?: number }>;
  connector_ids?: string[];
  footprint?: { clearance_h_m?: number; aabb?: { length_m?: number; width_m?: number } };
  params?: { geometry?: Record<string, number> };
  meta?: { visual_height_m?: number; proxy?: boolean };
};

export const EQUIPS: Record<string, Equip> = {
  "AUX-FIRE-01": auxFire as Equip,
  "AUX-WALL-01": auxWall as Equip,
  "IN-BUF-01": inBuf as Equip,
  "IN-DOCK-01": inDock as Equip,
  "MH-FORK-01": mhFork as Equip,
  "MH-HAND-01": mhHand as Equip,
  "OUT-BUF-01": outBuf as Equip,
  "OUT-DOCK-01": outDock as Equip,
  "OUT-FULL-01": outFull as Equip,
  "OUT-PACK-01": outPack as Equip,
  "PK-DEPAL-01": pkDepal as Equip,
  "PK-PUT-EACH-01": pkPut as Equip,
  "PK-STA-01": pkSta as Equip,
  "ST-FLOOR-01": stFloor as Equip,
  "ST-PAL-01": stPal as Equip,
};

/** True lod1 URL when this library id is mounted as GLB (not SVG proxy). */
export function realGlbUrl(typeId: string): string | null {
  const equip = EQUIPS[typeId];
  if (!equip) return null;
  if (equip.meta?.proxy === true) return null;
  if (equip.visual?.proxy && equip.visual.proxy !== "none") return null;
  const url = equip.glb || equip.lod?.lod1;
  if (typeof url !== "string" || !url || url.startsWith("proxy:")) return null;
  return url;
}
