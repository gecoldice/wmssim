export type Segment = {
  t0: number;
  t1: number;
  fromPose?: { x: number; y: number };
  toPose?: { x: number; y: number };
};

export function positionAt(segments: Segment[], t: number): { x: number; y: number } | null {
  if (!segments.length) return null;
  const ordered = [...segments].sort((a, b) => a.t0 - b.t0);
  let last: { x: number; y: number } | null = ordered[0].fromPose ?? null;
  for (const segment of ordered) {
    if (!segment.fromPose || !segment.toPose) continue;
    if (t < segment.t0) return last ?? segment.fromPose;
    const span = segment.t1 - segment.t0;
    if (t <= segment.t1 && span > 0) {
      const u = (t - segment.t0) / span;
      return {
        x: segment.fromPose.x + (segment.toPose.x - segment.fromPose.x) * u,
        y: segment.fromPose.y + (segment.toPose.y - segment.fromPose.y) * u,
      };
    }
    last = segment.toPose;
  }
  return last;
}

export function routesFromSnapshot(snapshot: Record<string, unknown> | null) {
  if (!snapshot) return [];
  const elements = (snapshot.elements as Array<Record<string, unknown>> | undefined) ?? [];
  const nodes = new Map<string, { x: number; y: number }>();
  for (const el of elements) {
    if (el.kind !== "node") continue;
    const pose = el.pose as { x: number; y: number };
    nodes.set(String(el.elementId), { x: pose.x, y: pose.y });
  }
  const edges = (snapshot.edges as Array<Record<string, unknown>> | undefined) ?? [];
  const lines = [];
  for (const edge of edges) {
    const a = nodes.get(String(edge.from));
    const b = nodes.get(String(edge.to));
    if (!a || !b) continue;
    lines.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y });
  }
  return lines;
}
