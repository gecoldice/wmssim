/**
 * Hand-maintained TypeScript mirrors of contracts/schemas (M0).
 * Keep in sync with JSON Schema; later milestones may codegen from schema.
 *
 * Outer contractVersion = "0.3"
 * Snapshot / equip schema versions remain "0.2"
 */

export const CONTRACT_VERSION = "0.3" as const;
export const SNAPSHOT_SCHEMA_VERSION = "0.2" as const;
export const EQUIP_SCHEMA_VERSION = "0.2" as const;

export type RevisionRef = { id: string; revision: string };

export type Point2 = { x: number; y: number };

export type Project = {
  contractVersion: typeof CONTRACT_VERSION;
  id: string;
  name: string;
  unitSystem: "metric";
  createdAt: string;
};

export type LayoutSnapshotCoord = {
  origin: "facility_sw_corner";
  xAxis: "east";
  yAxis: "north";
  unit: "m";
  yawZero?: "+X";
};

export type SnapshotElementKind = "slot" | "station" | "node" | "dock" | "device";

export type LayoutSnapshot = {
  schemaVersion: typeof SNAPSHOT_SCHEMA_VERSION;
  layoutId: string;
  layoutRevision: string;
  exportedAt?: string;
  coord: LayoutSnapshotCoord;
  elements: Array<{
    elementId: string;
    typeElementId?: string;
    kind: SnapshotElementKind;
    pose: { x: number; y: number; yawDeg?: number; zM?: number };
    footprint: { w: number; d: number } | { polygon: Point2[] };
    labels?: string[];
    accessNodeId?: string;
    capacityPallets?: number;
    capacitySlots?: number;
  }>;
  edges: Array<{
    edgeId: string;
    from: string;
    to: string;
    lengthM: number;
    bidirectional: boolean;
    maxConcurrent?: number;
    speedFactor?: number;
  }>;
};

export type PlanningRequest = {
  contractVersion: typeof CONTRACT_VERSION;
  projectId: string;
  facilityRef: RevisionRef;
  baseVariantRef: RevisionRef;
  demandRef: RevisionRef;
  scope: { mode: "whole" | "region"; polygon?: unknown; boundaryPorts?: string[] };
  locks: Array<{ instanceId: string; fields: "all" | string[] }>;
  goals: string[];
  constraints: Record<string, unknown>;
  evaluationLevel: "quick" | "detailed";
  budget: {
    maxConfigurations: number;
    maxIterations: number;
    maxWallTimeSec: number;
    maxMemoryMb: number;
  };
  seed: number;
  catalogRef: RevisionRef;
  templateSetRef: RevisionRef;
  ruleSetRefs: RevisionRef[];
};

export type ErrorCode =
  | "INPUT_UNCONFIRMED"
  | "UNSUPPORTED_SCENARIO"
  | "GEOMETRY_INVALID"
  | "LOCK_CONFLICT"
  | "NO_ACCESS_NODE"
  | "ROUTE_UNREACHABLE"
  | "REVISION_CONFLICT"
  | "STALE_VALIDATION"
  | "INCOMPARABLE_RESULTS"
  | "PRICE_INCOMPLETE"
  | "SCORE_PROFILE_INVALID"
  | "COMPUTATION_FAILED";

export type ErrorResponse = {
  code: ErrorCode | string;
  message: string;
  details?: Record<string, unknown> | null;
  retryable: boolean;
  traceId?: string | null;
};

/** Plane (m) → world Y-up: (X,Y,Z)=(x, height, -y); yawY = 90 + yawDeg */
export function planeToWorld3d(
  pose: { x: number; y: number; yawDeg?: number },
  heightM = 0,
): { position: { x: number; y: number; z: number }; yawYDeg: number } {
  return {
    position: { x: pose.x, y: heightM, z: -pose.y },
    yawYDeg: 90 + (pose.yawDeg ?? 0),
  };
}
