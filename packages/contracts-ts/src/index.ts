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
  | "COMPUTATION_FAILED"
  | "NARROW_AISLE"
  | "LAYOUT_REVISION_MISMATCH"
  | "NOT_SIMULATION_READY";

export type ComparisonMode = "layout_only" | "whole_solution";

export type CostEstimateStatus = "complete" | "incomplete";

export type CostEstimateTotals = {
  currency: string;
  knownSubtotal: number;
  complete: boolean;
  capex?: number | null;
  total?: number | null;
  note?: string;
};

export const COST_ENGINE_VERSION = "m4-cost-0.1" as const;
export const COMPARE_ENGINE_VERSION = "m4-compare-0.1" as const;

export type ValidationStatus = "pass" | "warn" | "fail" | "unknown";

export type ValidationCheck = {
  checkId: string;
  ruleId: string;
  status: ValidationStatus;
  objectIds?: string[];
  message: string;
  evidence?: Record<string, unknown>;
  fixHint?: string | null;
};

export type ValidationReport = {
  contractVersion: typeof CONTRACT_VERSION;
  id: string;
  inputFingerprint?: string | null;
  status: ValidationStatus;
  checks: ValidationCheck[];
  ruleSetRefs: RevisionRef[];
  computedAt: string;
  layoutRef?: RevisionRef;
  facilityRef?: RevisionRef;
};

export type PrepareStatus = "draft" | "saved" | "ready" | "failed" | "stale";

export type PrepareResult = {
  prepareStatus: PrepareStatus;
  simulationReady: boolean;
  layoutRevision: string;
  inputFingerprint?: string;
  validationReport?: ValidationReport;
};

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
