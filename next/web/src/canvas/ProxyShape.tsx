import { localToWorld } from "./geom";
import type { LocalBox, ProxyModel, Seam } from "../proxy/extrude";

type Props = {
  model: ProxyModel;
  x: number;
  y: number;
  yawDeg: number;
  ppm: number;
  relief: boolean;
  stroke: string;
  strokePx: number;
  fill: string;
  fillAlpha: number;
  ghost?: boolean;
  badge?: boolean;
};

function lift(point: { x: number; y: number }, z: number, relief: boolean): { x: number; y: number } {
  if (!relief) return point;
  const rise = z * 0.42;
  return { x: point.x - rise * 0.42, y: point.y + rise };
}

function world(x: number, y: number, yaw: number, lx: number, ly: number, z: number, relief: boolean) {
  return lift(localToWorld(x, y, yaw, lx, ly), z, relief);
}

function face(points: Array<{ x: number; y: number }>): string {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

function BoxFace({
  box,
  x,
  y,
  yaw,
  relief,
  ppm,
  stroke,
  strokePx,
  fill,
  opacity,
}: {
  box: LocalBox;
  x: number;
  y: number;
  yaw: number;
  relief: boolean;
  ppm: number;
  stroke: string;
  strokePx: number;
  fill: string;
  opacity: number;
}) {
  const g = (lx: number, ly: number, z: number) => world(x, y, yaw, lx, ly, z, relief);
  const ground = [g(box.x0, box.y0, box.z0), g(box.x1, box.y0, box.z0), g(box.x1, box.y1, box.z0), g(box.x0, box.y1, box.z0)];
  const top = [g(box.x0, box.y0, box.z1), g(box.x1, box.y0, box.z1), g(box.x1, box.y1, box.z1), g(box.x0, box.y1, box.z1)];
  const width = strokePx / ppm;
  return (
    <g opacity={opacity}>
      {relief
        ? [0, 1, 2, 3].map((index) => {
            const next = (index + 1) % 4;
            return (
              <polygon
                key={index}
                points={face([ground[index], ground[next], top[next], top[index]])}
                fill={fill}
                stroke={stroke}
                strokeWidth={width}
              />
            );
          })
        : null}
      <polygon points={face(relief ? top : ground)} fill={fill} stroke={stroke} strokeWidth={width} />
    </g>
  );
}

function seamLine(model: ProxyModel, seam: Seam, x: number, y: number, yaw: number, relief: boolean) {
  if (seam.kind === "bay") {
    const a = world(x, y, yaw, seam.at, -model.widthM / 2, model.heightM, relief);
    const b = world(x, y, yaw, seam.at, model.widthM / 2, model.heightM, relief);
    return [a, b];
  }
  const z = seam.at;
  const a = world(x, y, yaw, -model.lengthM / 2, -model.widthM / 2, z, relief);
  const b = world(x, y, yaw, model.lengthM / 2, -model.widthM / 2, z, relief);
  return [a, b];
}

export function ProxyShape({ model, x, y, yawDeg, ppm, relief, stroke, strokePx, fill, fillAlpha, ghost, badge }: Props) {
  const corner = world(x, y, yawDeg, model.lengthM / 2, model.widthM / 2, model.heightM, relief);
  return (
    <g className="proxy-shape" data-proxy="box" data-type={model.typeId} data-features={model.features.join(" ")} pointerEvents={ghost ? "none" : "auto"}>
      <ellipse
        cx={x}
        cy={y}
        rx={model.lengthM / 2}
        ry={Math.max(0.15, model.widthM / 3)}
        fill="#1A2330"
        opacity={model.shadowAlpha}
      />
      {model.boxes.map((box, index) => (
        <BoxFace
          key={`${box.role}-${index}`}
          box={box}
          x={x}
          y={y}
          yaw={yawDeg}
          relief={relief}
          ppm={ppm}
          stroke={ghost ? stroke : stroke}
          strokePx={strokePx}
          fill={fill}
          opacity={ghost ? fillAlpha * 0.7 : fillAlpha}
        />
      ))}
      {model.seams.map((seam, index) => {
        const [a, b] = seamLine(model, seam, x, y, yawDeg, relief);
        return (
          <line
            key={`s-${index}`}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="#ffffff"
            strokeOpacity={0.55}
            strokeWidth={1 / ppm}
          />
        );
      })}
      {badge && model.badge ? (
        <g transform={`translate(${corner.x} ${corner.y}) scale(${1 / ppm} ${-1 / ppm})`} pointerEvents="none">
          <rect x={2} y={-16} width={36} height={16} rx={3} fill="#ffffff" fillOpacity={0.88} stroke="#C5CDD4" />
          <text x={20} y={-4} textAnchor="middle" fill="#5A6570" fontSize={12}>
            {model.badge}
          </text>
        </g>
      ) : null}
    </g>
  );
}
