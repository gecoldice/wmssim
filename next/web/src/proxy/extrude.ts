import { EQUIPS, type Equip } from "./equip-index";

export type Family =
  | "dock"
  | "buffer"
  | "rack"
  | "floor"
  | "station"
  | "putwall"
  | "aisle"
  | "fire"
  | "wall"
  | "conveyor"
  | "generic";

export type Palette = { fill: string; fillAlpha: number; stroke: string; shadowAlpha: number };

export const PALETTE: Record<Family, Palette> = {
  dock: { fill: "#A8C5E8", fillAlpha: 0.42, stroke: "#5B7FA6", shadowAlpha: 0.08 },
  buffer: { fill: "#E8D4A8", fillAlpha: 0.38, stroke: "#A68B5B", shadowAlpha: 0.07 },
  rack: { fill: "#C5CBD0", fillAlpha: 0.4, stroke: "#6E787E", shadowAlpha: 0.08 },
  floor: { fill: "#D4C4B0", fillAlpha: 0.38, stroke: "#8A7A68", shadowAlpha: 0.07 },
  station: { fill: "#B8D9C8", fillAlpha: 0.4, stroke: "#5F8F78", shadowAlpha: 0.08 },
  putwall: { fill: "#D2C2E0", fillAlpha: 0.4, stroke: "#7A6A90", shadowAlpha: 0.08 },
  aisle: { fill: "#DDE3E8", fillAlpha: 0.22, stroke: "#9AA7B0", shadowAlpha: 0.04 },
  fire: { fill: "#D0D6DB", fillAlpha: 0.35, stroke: "#7A858E", shadowAlpha: 0.06 },
  wall: { fill: "#D0D6DB", fillAlpha: 0.35, stroke: "#7A858E", shadowAlpha: 0.06 },
  conveyor: { fill: "#C5D0D6", fillAlpha: 0.38, stroke: "#6E7F88", shadowAlpha: 0.07 },
  generic: { fill: "#D0D6DB", fillAlpha: 0.35, stroke: "#7A858E", shadowAlpha: 0.06 },
};

export const INTERACTION = {
  hoverStroke: "#3D6B99",
  selectedStroke: "#2F6FED",
  conflictStroke: "#C44B4B",
  conflictFill: "#E8B4B0",
};

export type LocalBox = {
  role: string;
  x0: number;
  x1: number;
  y0: number;
  y1: number;
  z0: number;
  z1: number;
};

export type Seam = { kind: "bay" | "level" | "layer"; at: number };

export type ProxyModel = {
  typeId: string;
  lengthM: number;
  widthM: number;
  heightM: number;
  fill: string;
  fillAlpha: number;
  stroke: string;
  shadowAlpha: number;
  badge: "代理" | null;
  boxes: LocalBox[];
  seams: Seam[];
  features: string[];
};

export type PoseSize = {
  lengthM: number;
  widthM: number;
  heightM: number;
  bays?: number;
  levels?: number;
};

function num(bag: Record<string, number> | undefined, key: string, fallback: number): number {
  const value = bag?.[key];
  return typeof value === "number" && value > 0 ? value : fallback;
}

export function familyOf(typeId: string): Family {
  if (typeId.startsWith("CV-")) return "conveyor";
  if (typeId === "AUX-FIRE-01") return "fire";
  if (typeId === "AUX-WALL-01" || typeId === "AUX-RAIL-01" || typeId === "AUX-GATE-01") return "wall";
  if (typeId === "IN-DOCK-01" || typeId === "OUT-DOCK-01" || typeId === "IN-RTN-01") return "dock";
  if (
    typeId === "IN-BUF-01" ||
    typeId === "OUT-BUF-01" ||
    typeId === "IN-STAGE-01" ||
    typeId === "PK-DEPAL-BUF-01" ||
    typeId === "PK-TOTE-BUF-01" ||
    typeId === "OUT-HOLD-01" ||
    typeId === "ST-OVF-01" ||
    typeId === "ST-SLOW-01" ||
    typeId === "AUX-EMPTY-PAL-01"
  ) {
    return "buffer";
  }
  if (typeId === "ST-FLOOR-01") return "floor";
  if (typeId.startsWith("ST-")) return "rack";
  if (
    typeId === "PK-PUT-EACH-01" ||
    typeId === "PK-BIN-FACE-01" ||
    typeId === "PK-WALL-01" ||
    typeId === "PK-SLOT-01" ||
    typeId === "PK-PTL-01" ||
    typeId === "OUT-CARR-01"
  ) {
    return "putwall";
  }
  if (typeId === "OUT-FULL-01" || typeId === "OUT-STG-01") return "buffer";
  if (
    typeId === "MH-HAND-01" ||
    typeId === "MH-FORK-01" ||
    typeId === "MH-AGV-01" ||
    typeId === "MH-CART-01" ||
    typeId === "MH-WAIT-01" ||
    typeId === "PK-VOICE-01" ||
    typeId === "AUX-ZONE-01"
  ) {
    return "aisle";
  }
  if (
    typeId.startsWith("PK-") ||
    typeId === "OUT-PACK-01" ||
    typeId === "IN-CHK-01" ||
    typeId === "IN-QC-01" ||
    typeId === "AUX-DESK-01"
  ) {
    return "station";
  }
  return "generic";
}

export function badgeFor(equip: { visual?: { proxy?: string }; lod?: { lod1?: string } } | null): "代理" | null {
  if (!equip) return "代理";
  if (equip.visual?.proxy === "none") return null;
  if (equip.visual?.proxy === "box") return "代理";
  if (typeof equip.lod?.lod1 === "string" && equip.lod.lod1.startsWith("proxy:")) return "代理";
  return "代理";
}

function featuresOf(boxes: LocalBox[], seams: Seam[], height: number): string[] {
  const roles = new Set(boxes.map((box) => box.role));
  const out: string[] = [];
  if (roles.has("step")) out.push("step");
  if (boxes.filter((box) => box.role === "jamb").length >= 2) out.push("opening");
  if (seams.some((seam) => seam.kind === "bay") || roles.has("post")) out.push("bay-seam");
  if (seams.some((seam) => seam.kind === "level")) out.push("level-seam");
  if (seams.some((seam) => seam.kind === "layer")) out.push("layer-seam");
  if (roles.has("leg") && roles.has("top")) out.push("tabletop");
  if (roles.has("rail")) out.push("rail");
  if (roles.has("leaf")) out.push("door");
  if (roles.has("belt")) out.push("belt");
  if (height <= 0.08) out.push("flat");
  if (height > 0.08 && height <= 0.3) out.push("low-slab");
  return out;
}

function shell(lengthM: number, widthM: number, heightM: number, role = "shell"): LocalBox {
  return { role, x0: -lengthM / 2, x1: lengthM / 2, y0: -widthM / 2, y1: widthM / 2, z0: 0, z1: heightM };
}

function buildBoxes(family: Family, lengthM: number, widthM: number, heightM: number, bays: number, levels: number): {
  boxes: LocalBox[];
  seams: Seam[];
  heightM: number;
} {
  const boxes: LocalBox[] = [];
  const seams: Seam[] = [];
  if (family === "dock") {
    const step = Math.min(1.2, Math.max(0.4, heightM > 2 ? 1.2 : heightM * 0.45));
    const door = Math.max(heightM, 4.5);
    boxes.push({ role: "step", x0: -lengthM / 2, x1: lengthM / 2, y0: -widthM / 2, y1: widthM / 2, z0: 0, z1: step });
    const gap = widthM * 0.85;
    const jamb = (widthM - gap) / 2;
    boxes.push({ role: "jamb", x0: -lengthM / 2, x1: lengthM / 2, y0: -widthM / 2, y1: -widthM / 2 + jamb, z0: step, z1: door });
    boxes.push({ role: "jamb", x0: -lengthM / 2, x1: lengthM / 2, y0: widthM / 2 - jamb, y1: widthM / 2, z0: step, z1: door });
    boxes.push({ role: "lintel", x0: lengthM / 2 - lengthM * 0.2, x1: lengthM / 2, y0: -widthM / 2, y1: widthM / 2, z0: door - 0.35, z1: door });
    return { boxes, seams, heightM: door };
  }
  if (family === "buffer") {
    const slab = Math.min(0.15, heightM * 0.08);
    boxes.push(shell(lengthM, widthM, Math.max(slab, 0.08), "slab"));
    const railH = 0.4;
    const t = 0.08;
    boxes.push({ role: "rail", x0: -lengthM / 2, x1: lengthM / 2, y0: -widthM / 2, y1: -widthM / 2 + t, z0: slab, z1: slab + railH });
    boxes.push({ role: "rail", x0: -lengthM / 2, x1: lengthM / 2, y0: widthM / 2 - t, y1: widthM / 2, z0: slab, z1: slab + railH });
    boxes.push({ role: "rail", x0: -lengthM / 2, x1: -lengthM / 2 + t, y0: -widthM / 2, y1: widthM / 2, z0: slab, z1: slab + railH });
    boxes.push({ role: "rail", x0: lengthM / 2 - t, x1: lengthM / 2, y0: -widthM / 2, y1: widthM / 2, z0: slab, z1: slab + railH });
    if (bays > 1) {
      for (let i = 1; i < bays; i += 1) seams.push({ kind: "bay", at: -lengthM / 2 + (lengthM / bays) * i });
    }
    for (let z = 0.9; z < heightM - 0.05; z += 0.9) seams.push({ kind: "layer", at: z });
    return { boxes, seams, heightM };
  }
  if (family === "rack") {
    boxes.push(shell(lengthM, widthM, heightM));
    const bayW = lengthM / Math.max(1, bays);
    for (let i = 1; i < bays; i += 1) seams.push({ kind: "bay", at: -lengthM / 2 + bayW * i });
    boxes.push({ role: "post", x0: -lengthM / 2, x1: -lengthM / 2 + 0.08, y0: -widthM / 2, y1: widthM / 2, z0: 0, z1: heightM });
    boxes.push({ role: "post", x0: lengthM / 2 - 0.08, x1: lengthM / 2, y0: -widthM / 2, y1: widthM / 2, z0: 0, z1: heightM });
    const levelH = heightM / Math.max(1, levels);
    for (let i = 1; i < levels; i += 1) seams.push({ kind: "level", at: levelH * i });
    return { boxes, seams, heightM };
  }
  if (family === "floor") {
    boxes.push(shell(lengthM, widthM, heightM));
    for (let z = 1; z < heightM - 0.05; z += 1) seams.push({ kind: "layer", at: z });
    return { boxes, seams, heightM };
  }
  if (family === "station") {
    const top = Math.min(0.9, Math.max(0.7, heightM - 0.2));
    const leg = 0.08;
    const corners = [
      [-lengthM / 2, -widthM / 2],
      [lengthM / 2 - leg, -widthM / 2],
      [-lengthM / 2, widthM / 2 - leg],
      [lengthM / 2 - leg, widthM / 2 - leg],
    ];
    for (const [x, y] of corners) {
      boxes.push({ role: "leg", x0: x, x1: x + leg, y0: y, y1: y + leg, z0: 0, z1: top });
    }
    boxes.push({
      role: "top",
      x0: -lengthM / 2 + 0.05,
      x1: lengthM / 2 - 0.05,
      y0: -widthM / 2 + 0.05,
      y1: widthM / 2 - 0.05,
      z0: top - 0.05,
      z1: top,
    });
    if (heightM > top + 0.2) {
      boxes.push({ role: "back", x0: -lengthM / 2, x1: -lengthM / 2 + 0.06, y0: -widthM / 2, y1: widthM / 2, z0: top, z1: heightM });
    }
    return { boxes, seams, heightM };
  }
  if (family === "putwall") {
    boxes.push(shell(lengthM, widthM, heightM));
    const count = Math.max(2, bays);
    for (let i = 1; i < count; i += 1) seams.push({ kind: "bay", at: -lengthM / 2 + (lengthM / count) * i });
    return { boxes, seams, heightM };
  }
  if (family === "aisle") {
    const flat = heightM >= 0.2 ? heightM : Math.min(0.08, Math.max(0.05, heightM || 0.06));
    boxes.push(shell(lengthM, widthM, flat, "flat"));
    return { boxes, seams, heightM: flat };
  }
  if (family === "fire") {
    const thin = Math.min(heightM, 0.15);
    boxes.push(shell(lengthM, widthM, thin, "flat"));
    return { boxes, seams, heightM: thin };
  }
  if (family === "wall") {
    const gap = Math.min(1.2, lengthM * 0.18);
    const leaf = (lengthM - gap) / 2;
    boxes.push({ role: "leaf", x0: -lengthM / 2, x1: -lengthM / 2 + leaf, y0: -widthM / 2, y1: widthM / 2, z0: 0, z1: heightM });
    boxes.push({ role: "leaf", x0: lengthM / 2 - leaf, x1: lengthM / 2, y0: -widthM / 2, y1: widthM / 2, z0: 0, z1: heightM });
    return { boxes, seams, heightM };
  }
  if (family === "conveyor") {
    boxes.push(shell(lengthM, widthM, Math.min(heightM, 0.9), "belt"));
    return { boxes, seams, heightM: Math.min(heightM, 0.9) };
  }
  boxes.push(shell(lengthM, widthM, heightM));
  return { boxes, seams, heightM };
}

export function interactionStyle(state: { hover?: boolean; selected?: boolean; conflict?: boolean }, base: Palette): {
  stroke: string;
  strokePx: number;
  fill: string;
  fillAlpha: number;
} {
  if (state.conflict) {
    return { stroke: INTERACTION.conflictStroke, strokePx: 2, fill: INTERACTION.conflictFill, fillAlpha: 0.45 };
  }
  if (state.selected) {
    return { stroke: INTERACTION.selectedStroke, strokePx: 2, fill: base.fill, fillAlpha: Math.min(0.55, base.fillAlpha + 0.08) };
  }
  if (state.hover) {
    return { stroke: INTERACTION.hoverStroke, strokePx: 1.5, fill: base.fill, fillAlpha: Math.min(0.55, base.fillAlpha + 0.06) };
  }
  return { stroke: base.stroke, strokePx: 1.25, fill: base.fill, fillAlpha: base.fillAlpha };
}

export function frameForZoom(model: ProxyModel, zoom: number): { lengthM: number; widthM: number; heightM: number; ppm: number; screenLengthPx: number } {
  const ppm = 16 * zoom;
  return {
    lengthM: model.lengthM,
    widthM: model.widthM,
    heightM: model.heightM,
    ppm,
    screenLengthPx: model.lengthM * ppm,
  };
}

function finish(typeId: string, lengthM: number, widthM: number, built: { boxes: LocalBox[]; seams: Seam[]; heightM: number }, badge: "代理" | null): ProxyModel {
  const family = familyOf(typeId);
  const palette = PALETTE[family];
  return {
    typeId,
    lengthM,
    widthM,
    heightM: built.heightM,
    fill: palette.fill,
    fillAlpha: palette.fillAlpha,
    stroke: palette.stroke,
    shadowAlpha: palette.shadowAlpha,
    badge,
    boxes: built.boxes,
    seams: built.seams,
    features: featuresOf(built.boxes, built.seams, built.heightM),
  };
}

export function buildPlaced(typeId: string, pose: PoseSize): ProxyModel {
  const family = familyOf(typeId);
  const bays = pose.bays && pose.bays > 0 ? pose.bays : family === "putwall" ? 6 : family === "rack" ? 1 : 1;
  const levels = pose.levels && pose.levels > 0 ? pose.levels : family === "rack" ? 4 : 1;
  let height = pose.heightM;
  if (family === "aisle" && typeId === "MH-FORK-01") height = 0.25;
  if (family === "aisle" && typeId !== "MH-FORK-01") height = 0.06;
  if (family === "fire") height = 0.15;
  const built = buildBoxes(family, pose.lengthM, pose.widthM, height, bays, levels);
  const equip = EQUIPS[typeId];
  return finish(typeId, pose.lengthM, pose.widthM, built, badgeFor(equip ?? null));
}

export function buildFromEquip(equip: Equip): ProxyModel {
  const geom = equip.params?.geometry || {};
  const id = equip.element_id;
  const family = familyOf(id);
  let lengthM = num(geom, "length_m", equip.footprint?.aabb?.length_m || 1);
  let widthM = num(geom, "width_m", equip.footprint?.aabb?.width_m || 1);
  const bays = num(geom, "bays", num(geom, "bay_count", family === "rack" ? 1 : 1));
  if (family === "rack" && geom.bay_w_m && geom.bays) {
    lengthM = geom.bay_w_m * geom.bays;
    widthM = num(geom, "bay_d_m", widthM);
  }
  if ((id === "OUT-FULL-01" || family === "buffer") && geom.bay_count && geom.bay_d_m && geom.bay_w_m) {
    lengthM = geom.bay_count * geom.bay_d_m;
    widthM = geom.bay_w_m;
  }
  let heightM = num(geom, "height_m", 0);
  if (!heightM && geom.levels && geom.level_height_m) heightM = geom.levels * geom.level_height_m;
  if (!heightM && geom.max_stack_h_m) heightM = geom.max_stack_h_m;
  if (!heightM && equip.meta?.visual_height_m) heightM = equip.meta.visual_height_m;
  if (!heightM) heightM = 1.5;
  if (id === "MH-HAND-01") heightM = 0.06;
  if (id === "MH-FORK-01") heightM = equip.meta?.visual_height_m || 0.25;
  const levels = num(geom, "levels", family === "rack" ? 4 : 1);
  const bayCount = id === "PK-PUT-EACH-01" ? num(geom, "bay_count", 6) : bays;
  const built = buildBoxes(family, lengthM, widthM, heightM, bayCount, levels);
  return finish(id, lengthM, widthM, built, badgeFor(equip));
}

export function portsNearFootprint(equip: Equip, slack = 1.5): boolean {
  const model = buildFromEquip(equip);
  for (const port of equip.ports || []) {
    const x = Math.abs(port.x_m || 0);
    const z = Math.abs(port.z_m || 0);
    if (x > model.widthM / 2 + slack) return false;
    if (z > model.lengthM / 2 + slack) return false;
  }
  return true;
}
