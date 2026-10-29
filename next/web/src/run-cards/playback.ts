export type Segment = {
  t0: number;
  t1: number;
  fromPose?: { x: number; y: number };
  toPose?: { x: number; y: number };
  resourceId?: string;
  taskId?: string;
};

export type Actor = {
  resourceId: string;
  taskId?: string;
  x: number;
  y: number;
};

function resourceKey(segment: Segment): string {
  return segment.resourceId || "resource";
}

function grouped(segments: Segment[]): Map<string, Segment[]> {
  const groups = new Map<string, Segment[]>();
  for (const segment of segments) {
    if (!segment.fromPose || !segment.toPose) continue;
    const key = resourceKey(segment);
    const list = groups.get(key);
    if (list) list.push(segment);
    else groups.set(key, [segment]);
  }
  for (const list of groups.values()) {
    list.sort((a, b) => a.t0 - b.t0 || a.t1 - b.t1);
  }
  return groups;
}

export function positionAt(segments: Segment[], t: number): { x: number; y: number } | null {
  const actors = actorsAt(segments, t);
  return actors[0] ? { x: actors[0].x, y: actors[0].y } : null;
}

/** One pose per resource, interpolated on that resource's own segments. */
export function actorsAt(segments: Segment[], t: number): Actor[] {
  const actors: Actor[] = [];
  for (const [resourceId, list] of grouped(segments)) {
    let pose = { ...list[0].fromPose! };
    let taskId = list[0].taskId;
    for (const segment of list) {
      const from = segment.fromPose!;
      const to = segment.toPose!;
      if (t < segment.t0) break;
      const span = segment.t1 - segment.t0;
      if (t <= segment.t1 && span > 0) {
        const u = (t - segment.t0) / span;
        pose = { x: from.x + (to.x - from.x) * u, y: from.y + (to.y - from.y) * u };
        taskId = segment.taskId;
        break;
      }
      pose = { ...to };
      taskId = segment.taskId;
    }
    actors.push({ resourceId, taskId, x: pose.x, y: pose.y });
  }
  return actors;
}

/** Points already traveled by one resource, ending at its pose at time t. */
export function trailOf(segments: Segment[], resourceId: string, t: number): Array<{ x: number; y: number }> {
  const list = grouped(segments).get(resourceId);
  if (!list) return [];
  const points: Array<{ x: number; y: number }> = [];
  for (const segment of list) {
    const from = segment.fromPose!;
    const to = segment.toPose!;
    if (segment.t0 > t) break;
    if (!points.length) points.push({ ...from });
    if (t >= segment.t1) {
      points.push({ ...to });
      continue;
    }
    const span = segment.t1 - segment.t0;
    const u = span > 0 ? (t - segment.t0) / span : 1;
    points.push({ x: from.x + (to.x - from.x) * u, y: from.y + (to.y - from.y) * u });
    break;
  }
  return points;
}

export function segmentBounds(segments: Segment[], horizonSec: number): { t0: number; t1: number } {
  const usable = segments.filter((segment) => segment.fromPose && segment.toPose);
  if (!usable.length) return { t0: 0, t1: Math.max(horizonSec, 1) };
  const t0 = Math.min(...usable.map((segment) => segment.t0));
  const t1 = Math.max(...usable.map((segment) => segment.t1));
  if (t1 <= t0) return { t0, t1: t0 + 1 };
  return { t0, t1 };
}
