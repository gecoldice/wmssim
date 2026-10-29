import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { ColumnMark, Guide, Tone } from "./geom";
import { columnBox, fireLaneInside, footprintCorners, localToWorld } from "./geom";
import { ProxyShape } from "./ProxyShape";
import { catalogItem } from "../library/catalog";
import { buildPlaced, interactionStyle } from "../proxy/extrude";
import type { Actor } from "../run-cards/playback";
import { trailOf, type Segment } from "../run-cards/playback";
import type { Draft, PoseEl } from "../workbench/draft";

export type Marker = { x: number; y: number };

export type CanvasHandle = {
  metersFromClient: (clientX: number, clientY: number) => { x: number; y: number } | null;
};

type Ghost = {
  typeId: string;
  clientX: number;
  clientY: number;
  x: number;
  y: number;
  lengthM: number;
  widthM: number;
  heightM: number;
  yawDeg: number;
  tone: Tone;
  label: string;
  detail?: string;
};

type Props = {
  draft: Draft;
  selected: string | null;
  conflictIds: string[];
  liveTone: { id: string; tone: Tone } | null;
  guides: Guide[];
  showGrid: boolean;
  showLinks: boolean;
  actors: Actor[];
  segments: Segment[];
  simT: number;
  relief: boolean;
  badge: string;
  interactive: boolean;
  ghost: Ghost | null;
  columns: ColumnMark[];
  alertColumnIds: string[];
  aisleAlert: boolean;
  fireLaneAlert: boolean;
  onSelect: (id: string | null) => void;
  onMove: (id: string, x: number, y: number, phase: "start" | "move" | "end") => void;
};

type Cam = { ppm: number; ox: number; oy: number };

const TONE_STROKE: Record<Tone, string> = {
  green: "#2f8f72",
  yellow: "#c4922e",
  red: "#ce5d50",
};

export const LayoutCanvas = forwardRef<CanvasHandle, Props>(function LayoutCanvas(
  {
    draft,
    selected,
    conflictIds,
    liveTone,
    guides,
    showGrid,
    showLinks,
    actors,
    segments,
    simT,
    relief,
    badge,
    interactive,
    ghost,
    columns,
    alertColumnIds,
    aisleAlert,
    fireLaneAlert,
    onSelect,
    onMove,
  },
  ref,
) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const [view, setView] = useState({ w: 960, h: 620 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hover, setHover] = useState<string | null>(null);
  const camRef = useRef<Cam>({ ppm: 16, ox: 80, oy: 500 });

  const width = Number(draft.widthM);
  const height = Number(draft.heightM);
  const sized = Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0;

  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const apply = () => {
      const rect = el.getBoundingClientRect();
      setView({ w: Math.max(280, rect.width), h: Math.max(220, rect.height) });
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const cam = camera(sized ? width : 40, sized ? height : 24, view.w, view.h, zoom, pan);
  camRef.current = cam;

  function metersFromClient(clientX: number, clientY: number): { x: number; y: number } | null {
    const svg = svgRef.current;
    if (!svg) return null;
    const point = svg.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    const matrix = svg.getScreenCTM();
    if (!matrix) return null;
    const mapped = point.matrixTransform(matrix.inverse());
    const current = camRef.current;
    return {
      x: (mapped.x - current.ox) / current.ppm,
      y: (current.oy - mapped.y) / current.ppm,
    };
  }

  useImperativeHandle(ref, () => ({ metersFromClient }));

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = svg.getBoundingClientRect();
      const sx = ((event.clientX - rect.left) / rect.width) * view.w;
      const sy = ((event.clientY - rect.top) / rect.height) * view.h;
      const before = camRef.current;
      const mx = (sx - before.ox) / before.ppm;
      const my = (before.oy - sy) / before.ppm;
      const factor = event.deltaY > 0 ? 0.9 : 1.1;
      const nextZoom = clamp(zoom * factor, 0.35, 6);
      const worldW = sized ? width : 40;
      const worldH = sized ? height : 24;
      const base = Math.min((view.w - 72) / worldW, (view.h - 72) / worldH);
      const nextPpm = base * nextZoom;
      const nextOx = sx - mx * nextPpm;
      const nextOy = sy + my * nextPpm;
      const centeredOx = view.w / 2 - (worldW / 2) * nextPpm;
      const centeredOy = view.h / 2 + (worldH / 2) * nextPpm;
      setZoom(nextZoom);
      setPan({ x: nextOx - centeredOx, y: nextOy - centeredOy });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoom, view.w, view.h, width, height, sized]);

  function onBackground(event: ReactPointerEvent) {
    if ((event.target as Element).closest?.(".board-item")) return;
    const origin = { ...pan };
    const startX = event.clientX;
    const startY = event.clientY;
    let moved = false;
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (Math.hypot(dx, dy) > 3) moved = true;
      const rect = svgRef.current?.getBoundingClientRect();
      const scaleX = rect ? view.w / rect.width : 1;
      const scaleY = rect ? view.h / rect.height : 1;
      setPan({ x: origin.x + dx * scaleX, y: origin.y + dy * scaleY });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (!moved) onSelect(null);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  const gridStep = cam.ppm > 22 ? 1 : 5;
  const aisleY = Number(draft.aisleY);
  const aisleFrom = Number(draft.aisleFromX);
  const aisleTo = Number(draft.aisleToX);
  const aisleW = Number(draft.aisleWidthM);
  const showAisle = Number.isFinite(aisleY) && Number.isFinite(aisleFrom) && Number.isFinite(aisleTo);
  const barM = sized && width >= 20 ? 5 : 2;
  const lane = sized ? fireLaneInside(width, height) : null;

  return (
    <div className="board-wrap">
      <div className="board-frame" ref={frameRef}>
        <svg
          ref={svgRef}
          className="board"
          viewBox={`0 0 ${view.w} ${view.h}`}
          aria-label="综合仓米制布局"
          onPointerDown={onBackground}
        >
          <rect x={0} y={0} width={view.w} height={view.h} fill="#EEF1F4" />
          <g transform={`translate(${cam.ox} ${cam.oy}) scale(${cam.ppm} ${-cam.ppm})`}>
            {sized ? (
              <rect x={0} y={0} width={width} height={height} fill="#EEF1F4" stroke="#9AA7B0" strokeWidth={1.2 / cam.ppm} />
            ) : null}
            {sized && showGrid
              ? gridLines(width, height, gridStep).map((line) => (
                  <line
                    key={line.key}
                    x1={line.x1}
                    y1={line.y1}
                    x2={line.x2}
                    y2={line.y2}
                    stroke="#D5DCE3"
                    strokeWidth={1 / cam.ppm}
                  />
                ))
              : null}
            {sized && showAisle ? (
              <g>
                <rect
                  x={Math.min(aisleFrom, aisleTo)}
                  y={aisleY - (Number.isFinite(aisleW) ? aisleW : 3) / 2}
                  width={Math.abs(aisleTo - aisleFrom)}
                  height={Number.isFinite(aisleW) ? aisleW : 3}
                  fill={aisleAlert ? "#fff5f3" : "#ffffff"}
                  stroke={aisleAlert ? "#ce5d50" : "#d0dcda"}
                  strokeWidth={(aisleAlert ? 2.4 : 1) / cam.ppm}
                />
                <line
                  x1={aisleFrom}
                  y1={aisleY}
                  x2={aisleTo}
                  y2={aisleY}
                  stroke="#a8c7c1"
                  strokeWidth={1.2 / cam.ppm}
                  strokeDasharray={`${0.45} ${0.35}`}
                />
              </g>
            ) : null}
            {lane ? (
              <g pointerEvents="none">
                <rect
                  x={lane.minX}
                  y={lane.minY}
                  width={lane.maxX - lane.minX}
                  height={lane.maxY - lane.minY}
                  fill={fireLaneAlert ? "#f6d2cc" : "#f8ead2"}
                  stroke={fireLaneAlert ? "#ce5d50" : "#d7b56a"}
                  strokeWidth={(fireLaneAlert ? 2.2 : 1) / cam.ppm}
                />
                <g transform={`translate(${(lane.minX + lane.maxX) / 2} ${(lane.minY + lane.maxY) / 2}) scale(${1 / cam.ppm} ${-1 / cam.ppm})`}>
                  <text textAnchor="middle" fill="#8a6230" fontSize={11}>
                    疏散带
                  </text>
                </g>
              </g>
            ) : null}
            {sized
              ? columns.map((col) => {
                  const box = columnBox(col);
                  const alert = alertColumnIds.includes(col.id);
                  return (
                    <g key={col.id} pointerEvents="none">
                      <rect
                        x={box.minX}
                        y={box.minY}
                        width={col.sizeM}
                        height={col.sizeM}
                        fill={alert ? "#f6d5d0" : "#f3ead8"}
                        stroke={alert ? "#ce5d50" : "#8a704c"}
                        strokeWidth={(alert ? 2.4 : 1.2) / cam.ppm}
                      />
                      <line
                        x1={box.minX}
                        y1={col.y}
                        x2={box.maxX}
                        y2={col.y}
                        stroke={alert ? "#ce5d50" : "#8a704c"}
                        strokeWidth={1 / cam.ppm}
                      />
                      <line
                        x1={col.x}
                        y1={box.minY}
                        x2={col.x}
                        y2={box.maxY}
                        stroke={alert ? "#ce5d50" : "#8a704c"}
                        strokeWidth={1 / cam.ppm}
                      />
                    </g>
                  );
                })
              : null}
            {guides.map((guide, index) => (
              <line
                key={`g${index}`}
                x1={guide.x1}
                y1={guide.y1}
                x2={guide.x2}
                y2={guide.y2}
                stroke="#c4a15a"
                strokeWidth={1.2 / cam.ppm}
                strokeDasharray={`${0.25} ${0.2}`}
              />
            ))}
            {sized
              ? [...draft.elements]
                  .sort((a, b) => b.y - a.y || a.x - b.x)
                  .map((el) => (
                    <Item
                      key={el.instanceId}
                      el={el}
                      ppm={cam.ppm}
                      relief={relief}
                      selected={selected === el.instanceId}
                      hovered={hover === el.instanceId}
                      conflict={conflictIds.includes(el.instanceId)}
                      tone={liveTone?.id === el.instanceId ? liveTone.tone : null}
                      showLinks={showLinks}
                      interactive={interactive}
                      metersFromClient={metersFromClient}
                      onSelect={onSelect}
                      onMove={onMove}
                      onHover={setHover}
                    />
                  ))
              : null}
            {ghost && sized ? (
              <GhostProxy ghost={ghost} ppm={cam.ppm} relief={relief} />
            ) : null}
            {actors.map((actor) => {
              const trail = trailOf(segments, actor.resourceId, simT);
              const heading = headingOf(trail);
              return (
                <g key={actor.resourceId}>
                  {trail.length > 1 ? (
                    <polyline
                      points={trail.map((p) => `${p.x},${p.y}`).join(" ")}
                      fill="none"
                      stroke="#d8855c"
                      strokeWidth={2.2 / cam.ppm}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  ) : null}
                  <ProxyBox
                    x={actor.x}
                    y={actor.y}
                    lengthM={1.2}
                    widthM={0.8}
                    heightM={1.5}
                    yawDeg={heading}
                    fill="#e58a57"
                    stroke="#9a5a32"
                    ppm={cam.ppm}
                    relief
                    label={actor.resourceId}
                    detail={actor.taskId ?? "行驶"}
                  />
                </g>
              );
            })}
          </g>
        </svg>
        <div className="board-badge">
          <span className="green-dot" />
          <span>{badge}</span>
        </div>
        <div className="canvas-legend">
          <i className="swatch green" /> 可放
          <i className="swatch yellow" /> 注意
          <i className="swatch red" /> 拒绝
        </div>
        <div className="board-scale">
          <span style={{ display: "block", width: barM * cam.ppm, borderTop: "2px solid #536d70", marginBottom: 4 }} />
          {barM} m
        </div>
        <div className="zoom-controls">
          <button type="button" aria-label="放大" onClick={() => setZoom((value) => clamp(value * 1.2, 0.35, 6))}>
            +
          </button>
          <button type="button" aria-label="缩小" onClick={() => setZoom((value) => clamp(value / 1.2, 0.35, 6))}>
            −
          </button>
          <button
            type="button"
            aria-label="适配场地"
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
          >
            适
          </button>
        </div>
      </div>
    </div>
  );
});

function camera(worldW: number, worldH: number, viewW: number, viewH: number, zoom: number, pan: { x: number; y: number }): Cam {
  const base = Math.min((viewW - 72) / worldW, (viewH - 72) / worldH);
  const ppm = base * zoom;
  return {
    ppm,
    ox: viewW / 2 - (worldW / 2) * ppm + pan.x,
    oy: viewH / 2 + (worldH / 2) * ppm + pan.y,
  };
}

function clamp(value: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, value));
}

function gridLines(width: number, height: number, step: number) {
  const lines: Array<{ key: string; x1: number; y1: number; x2: number; y2: number }> = [];
  for (let x = 0; x <= width + 1e-6; x += step) {
    lines.push({ key: `x${x}`, x1: x, y1: 0, x2: x, y2: height });
  }
  for (let y = 0; y <= height + 1e-6; y += step) {
    lines.push({ key: `y${y}`, x1: 0, y1: y, x2: width, y2: y });
  }
  return lines;
}

function headingOf(trail: Array<{ x: number; y: number }>): number {
  if (trail.length < 2) return 0;
  const a = trail[trail.length - 2];
  const b = trail[trail.length - 1];
  return (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI;
}

function GhostProxy({ ghost, ppm, relief }: { ghost: Ghost; ppm: number; relief: boolean }) {
  const model = buildPlaced(ghost.typeId, { lengthM: ghost.lengthM, widthM: ghost.widthM, heightM: ghost.heightM });
  return (
    <g>
      <ProxyShape
        model={model}
        x={ghost.x}
        y={ghost.y}
        yawDeg={ghost.yawDeg}
        ppm={ppm}
        relief={relief}
        stroke={TONE_STROKE[ghost.tone]}
        strokePx={2}
        fill={model.fill}
        fillAlpha={model.fillAlpha}
        ghost
      />
      <g transform={`translate(${ghost.x} ${ghost.y}) scale(${1 / ppm} ${-1 / ppm})`} pointerEvents="none">
        <text y={-8} textAnchor="middle" fill="#294246" fontSize={12} fontWeight={700}>
          {ghost.label}
        </text>
        <text y={8} textAnchor="middle" fill="#5A6570" fontSize={10}>
          {ghost.detail || (ghost.tone === "green" ? "可放" : ghost.tone === "yellow" ? "注意" : "拒绝")}
        </text>
      </g>
    </g>
  );
}

function Item({
  el,
  ppm,
  relief,
  selected,
  hovered,
  conflict,
  tone,
  showLinks,
  interactive,
  metersFromClient,
  onSelect,
  onMove,
  onHover,
}: {
  el: PoseEl;
  ppm: number;
  relief: boolean;
  selected: boolean;
  hovered: boolean;
  conflict: boolean;
  tone: Tone | null;
  showLinks: boolean;
  interactive: boolean;
  metersFromClient: (clientX: number, clientY: number) => { x: number; y: number } | null;
  onSelect: (id: string | null) => void;
  onMove: (id: string, x: number, y: number, phase: "start" | "move" | "end") => void;
  onHover: (id: string | null) => void;
}) {
  const spec = catalogItem(el.typeElementId);
  const model = buildPlaced(el.typeElementId, {
    lengthM: el.lengthM,
    widthM: el.widthM,
    heightM: el.heightM,
    bays: el.bays,
    levels: el.levels,
  });
  const look = interactionStyle(
    { hover: hovered && !selected && !conflict && !tone, selected: selected && !conflict && !tone, conflict: conflict && !tone },
    { fill: model.fill, fillAlpha: model.fillAlpha, stroke: model.stroke, shadowAlpha: model.shadowAlpha },
  );
  const stroke = tone ? TONE_STROKE[tone] : look.stroke;
  return (
    <g
      className={`board-item${selected ? " selected" : ""}${conflict ? " conflict" : ""}`}
      onPointerEnter={() => onHover(el.instanceId)}
      onPointerLeave={() => onHover(null)}
      onPointerDown={(event) => {
        if (!interactive) return;
        event.stopPropagation();
        onSelect(el.instanceId);
        const origin = { x: el.x, y: el.y };
        const start = metersFromClient(event.clientX, event.clientY);
        if (!start) return;
        onMove(el.instanceId, el.x, el.y, "start");
        const move = (ev: PointerEvent) => {
          const now = metersFromClient(ev.clientX, ev.clientY);
          if (!now) return;
          onMove(el.instanceId, origin.x + (now.x - start.x), origin.y + (now.y - start.y), "move");
        };
        const up = (ev: PointerEvent) => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          const now = metersFromClient(ev.clientX, ev.clientY);
          const x = now ? origin.x + (now.x - start.x) : origin.x;
          const y = now ? origin.y + (now.y - start.y) : origin.y;
          onMove(el.instanceId, x, y, "end");
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
      }}
    >
      {showLinks && el.accessX !== null && el.accessY !== null ? (
        <line
          x1={el.x}
          y1={el.y}
          x2={el.accessX}
          y2={el.accessY}
          stroke="#a8c7c1"
          strokeWidth={1 / ppm}
          strokeDasharray={`${0.2} ${0.15}`}
        />
      ) : null}
      <ProxyShape
        model={model}
        x={el.x}
        y={el.y}
        yawDeg={el.yawDeg}
        ppm={ppm}
        relief={relief}
        stroke={stroke}
        strokePx={tone ? 2.2 : look.strokePx}
        fill={look.fill}
        fillAlpha={look.fillAlpha}
        badge
      />
      <g transform={`translate(${el.x} ${el.y + (relief ? model.heightM * 0.42 : 0)}) scale(${1 / ppm} ${-1 / ppm})`} pointerEvents="none">
        <text y={-6} textAnchor="middle" fill="#294246" fontSize={12} fontWeight={700}>
          {spec?.name ?? el.typeElementId}
        </text>
        <text y={10} textAnchor="middle" fill="#5A6570" fontSize={10}>
          {`${el.instanceId} · ${trim(el.lengthM)}×${trim(el.widthM)} m`}
        </text>
      </g>
    </g>
  );
}

function ProxyBox({
  x,
  y,
  lengthM,
  widthM,
  heightM,
  yawDeg,
  fill,
  stroke,
  ppm,
  relief,
  ghost,
  label,
  detail,
  levels,
  selected,
}: {
  x: number;
  y: number;
  lengthM: number;
  widthM: number;
  heightM: number;
  yawDeg: number;
  fill: string;
  stroke: string;
  ppm: number;
  relief: boolean;
  ghost?: boolean;
  label: string;
  detail: string;
  levels?: number;
  selected?: boolean;
}) {
  const ground = footprintCorners(x, y, lengthM, widthM, yawDeg);
  const lift = relief ? heightM * 0.42 : 0;
  const offset = { x: -lift * 0.42, y: lift };
  const top = ground.map((corner) => ({ x: corner.x + offset.x, y: corner.y + offset.y }));
  const opacity = ghost ? 0.42 : 0.94;
  const faces = relief
    ? [0, 1, 2, 3].map((index) => {
        const next = (index + 1) % 4;
        return [ground[index], ground[next], top[next], top[index]];
      })
    : [];
  return (
    <g opacity={opacity} pointerEvents={ghost ? "none" : "auto"}>
      {faces.map((face, index) => (
        <polygon
          key={index}
          points={pts(face)}
          fill={shade(fill, 0.55 + (index % 2) * 0.12)}
          stroke={stroke}
          strokeWidth={(selected ? 2.2 : 1) / ppm}
        />
      ))}
      <polygon points={pts(relief ? top : ground)} fill={fill} stroke={stroke} strokeWidth={(ghost || selected ? 2.4 : 1.2) / ppm} />
      {relief && levels && levels > 1
        ? Array.from({ length: levels - 1 }, (_, level) => {
            const t = ((level + 1) / levels) * lift;
            const a = localToWorld(x, y, yawDeg, -lengthM / 2, widthM / 2);
            const b = localToWorld(x, y, yawDeg, lengthM / 2, widthM / 2);
            const shift = { x: -t * 0.42, y: t };
            return (
              <line
                key={level}
                x1={a.x + shift.x}
                y1={a.y + shift.y}
                x2={b.x + shift.x}
                y2={b.y + shift.y}
                stroke="rgba(80, 110, 106, 0.35)"
                strokeWidth={1 / ppm}
              />
            );
          })
        : null}
      <g transform={`translate(${x + offset.x} ${y + offset.y}) scale(${1 / ppm} ${-1 / ppm})`} pointerEvents="none">
        <text y={-6} textAnchor="middle" fill="#294246" fontSize={12} fontWeight={700}>
          {label}
        </text>
        <text y={10} textAnchor="middle" fill="#748e90" fontSize={10}>
          {detail}
        </text>
      </g>
    </g>
  );
}

function pts(points: Array<{ x: number; y: number }>): string {
  return points.map((p) => `${p.x},${p.y}`).join(" ");
}

function shade(hex: string, factor: number): string {
  const raw = hex.replace("#", "");
  if (raw.length !== 6) return hex;
  const channels = [0, 2, 4].map((index) => Math.round(parseInt(raw.slice(index, index + 2), 16) * factor));
  return `#${channels.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function trim(value: number): string {
  return String(Math.round(value * 100) / 100);
}
