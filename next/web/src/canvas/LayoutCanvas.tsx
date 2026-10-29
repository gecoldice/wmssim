import { useRef, type PointerEvent as ReactPointerEvent } from "react";
import { catalogItem } from "../library/catalog";
import type { Draft, PoseEl } from "../workbench/draft";

export type RouteLine = { x1: number; y1: number; x2: number; y2: number };
export type Marker = { x: number; y: number };

type Props = {
  draft: Draft;
  selected: string | null;
  pending: string | null;
  conflictIds: string[];
  showGrid: boolean;
  showRoute: boolean;
  routes: RouteLine[];
  marker: Marker | null;
  badge: string;
  interactive: boolean;
  onPlace: (x: number, y: number) => void;
  onSelect: (id: string | null) => void;
  onMove: (id: string, x: number, y: number, phase: "start" | "move" | "end") => void;
};

const VB_W = 1000;
const VB_H = 630;
const PAD = 72;

function metrics(draft: Draft) {
  const width = Number(draft.widthM);
  const height = Number(draft.heightM);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  const s = Math.min((VB_W - PAD * 2) / width, (VB_H - PAD * 2) / height);
  return { width, height, s };
}

function toSvg(x: number, y: number, _width: number, height: number, s: number) {
  return { X: PAD + x * s, Y: PAD + (height - y) * s };
}

function fromSvg(X: number, Y: number, _width: number, height: number, s: number) {
  return { x: (X - PAD) / s, y: height - (Y - PAD) / s };
}

export function LayoutCanvas({
  draft,
  selected,
  pending,
  conflictIds,
  showGrid,
  showRoute,
  routes,
  marker,
  badge,
  interactive,
  onPlace,
  onSelect,
  onMove,
}: Props) {
  const ref = useRef<SVGSVGElement | null>(null);
  const frame = metrics(draft);
  const scaleLabel = frame ? `${Math.max(1, Math.round(frame.width / 8))} m` : "—";
  const bar = frame ? Math.min(frame.width / 4, 10) : 10;

  function localPoint(event: ReactPointerEvent | PointerEvent) {
    const svg = ref.current;
    if (!svg) return { X: 0, Y: 0 };
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = svg.getScreenCTM();
    if (!matrix) return { X: 0, Y: 0 };
    const mapped = point.matrixTransform(matrix.inverse());
    return { X: mapped.x, Y: mapped.y };
  }

  function onBackground(event: ReactPointerEvent) {
    if (!interactive || !frame) return;
    if ((event.target as Element).closest?.(".board-item")) return;
    const { X, Y } = localPoint(event);
    const meters = fromSvg(X, Y, frame.width, frame.height, frame.s);
    if (pending) onPlace(meters.x, meters.y);
    else onSelect(null);
  }

  return (
    <div className="board-wrap">
      <div className="board-frame">
        <svg ref={ref} className="board" viewBox={`0 0 ${VB_W} ${VB_H}`} aria-label="综合仓顶视布局" onPointerDown={onBackground}>
          <rect x={0} y={0} width={VB_W} height={VB_H} className="board-bg" />
          {frame && showGrid
            ? Array.from({ length: Math.floor(frame.width / 5) + 1 }, (_, i) => {
                const p = toSvg(i * 5, 0, frame.width, frame.height, frame.s);
                const top = toSvg(i * 5, frame.height, frame.width, frame.height, frame.s);
                return <line key={`gx${i}`} x1={p.X} y1={p.Y} x2={top.X} y2={top.Y} className="grid-line" />;
              })
            : null}
          {frame && showGrid
            ? Array.from({ length: Math.floor(frame.height / 5) + 1 }, (_, i) => {
                const p = toSvg(0, i * 5, frame.width, frame.height, frame.s);
                const right = toSvg(frame.width, i * 5, frame.width, frame.height, frame.s);
                return <line key={`gy${i}`} x1={p.X} y1={p.Y} x2={right.X} y2={right.Y} className="grid-line" />;
              })
            : null}
          {frame ? (
            <rect
              x={PAD}
              y={PAD}
              width={frame.width * frame.s}
              height={frame.height * frame.s}
              fill="#f5f8f6"
              stroke="#738d8d"
              strokeWidth={4}
            />
          ) : null}
          {frame && draft.aisleFromX && draft.aisleToX && draft.aisleY
            ? (() => {
                const y = Number(draft.aisleY);
                const x1 = Number(draft.aisleFromX);
                const x2 = Number(draft.aisleToX);
                const a = toSvg(x1, y, frame.width, frame.height, frame.s);
                const b = toSvg(x2, y, frame.width, frame.height, frame.s);
                const width = Number(draft.aisleWidthM);
                return (
                  <line
                    x1={a.X}
                    y1={a.Y}
                    x2={b.X}
                    y2={b.Y}
                    stroke="#d0dcda"
                    strokeWidth={Number.isFinite(width) ? Math.max(6, width * frame.s) : 8}
                  />
                );
              })()
            : null}
          {frame && showRoute
            ? routes.map((line, index) => {
                const a = toSvg(line.x1, line.y1, frame.width, frame.height, frame.s);
                const b = toSvg(line.x2, line.y2, frame.width, frame.height, frame.s);
                return (
                  <line
                    key={index}
                    x1={a.X}
                    y1={a.Y}
                    x2={b.X}
                    y2={b.Y}
                    className="route"
                  />
                );
              })
            : null}
          {frame
            ? draft.elements.map((el) => (
                <Item
                  key={el.instanceId}
                  el={el}
                  frame={frame}
                  selected={selected === el.instanceId}
                  conflict={conflictIds.includes(el.instanceId)}
                  interactive={interactive}
                  localPoint={localPoint}
                  onSelect={onSelect}
                  onMove={onMove}
                />
              ))
            : null}
          {frame && marker ? (
            <circle
              cx={toSvg(marker.x, marker.y, frame.width, frame.height, frame.s).X}
              cy={toSvg(marker.x, marker.y, frame.width, frame.height, frame.s).Y}
              r={7}
              fill="#e58a57"
              stroke="#fff"
              strokeWidth={2}
            />
          ) : null}
        </svg>
        <div className="board-badge">
          <span className="green-dot" />
          <span>{badge}</span>
        </div>
        <div className="board-scale" style={{ width: frame ? undefined : undefined }}>
          <span style={{ display: "block", width: frame ? bar * frame.s : 40, borderTop: "2px solid #536d70", marginBottom: 4 }} />
          {scaleLabel}
        </div>
      </div>
    </div>
  );
}

function Item({
  el,
  frame,
  selected,
  conflict,
  interactive,
  localPoint,
  onSelect,
  onMove,
}: {
  el: PoseEl;
  frame: { width: number; height: number; s: number };
  selected: boolean;
  conflict: boolean;
  interactive: boolean;
  localPoint: (event: ReactPointerEvent | PointerEvent) => { X: number; Y: number };
  onSelect: (id: string | null) => void;
  onMove: (id: string, x: number, y: number, phase: "start" | "move" | "end") => void;
}) {
  const spec = catalogItem(el.typeElementId);
  const w = spec?.w ?? 2;
  const d = spec?.d ?? 1;
  const center = toSvg(el.x, el.y, frame.width, frame.height, frame.s);
  const fill = el.typeElementId === "ST-PAL-01" ? "#bfded7" : "#d3dee8";
  return (
    <g
      className={`board-item${selected ? " selected" : ""}${conflict ? " conflict" : ""}`}
      transform={`translate(${center.X - (w * frame.s) / 2} ${center.Y - (d * frame.s) / 2})`}
      onPointerDown={(event) => {
        if (!interactive) return;
        event.stopPropagation();
        onSelect(el.instanceId);
        const origin = { ...el };
        const start = localPoint(event);
        onMove(el.instanceId, el.x, el.y, "start");
        const move = (ev: PointerEvent) => {
          const now = localPoint(ev);
          const dx = (now.X - start.X) / frame.s;
          const dy = -(now.Y - start.Y) / frame.s;
          const x = Math.round((origin.x + dx) * 10) / 10;
          const y = Math.round((origin.y + dy) * 10) / 10;
          onMove(el.instanceId, x, y, "move");
        };
        const up = (ev: PointerEvent) => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          const now = localPoint(ev);
          const dx = (now.X - start.X) / frame.s;
          const dy = -(now.Y - start.Y) / frame.s;
          const x = Math.round((origin.x + dx) * 10) / 10;
          const y = Math.round((origin.y + dy) * 10) / 10;
          onMove(el.instanceId, x, y, "end");
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
      }}
    >
      <rect width={w * frame.s} height={d * frame.s} rx={2} fill={fill} className="item-outline" />
      <text x={(w * frame.s) / 2} y={d * frame.s + 14} textAnchor="middle" className="item-label">
        {spec?.name ?? el.typeElementId}
      </text>
      <text x={(w * frame.s) / 2} y={d * frame.s + 26} textAnchor="middle" className="item-detail">
        {el.instanceId}
      </text>
    </g>
  );
}
