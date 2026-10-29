import { useState } from "react";
import {
  CONTRACT_VERSION,
  EQUIP_SCHEMA_VERSION,
  SNAPSHOT_SCHEMA_VERSION,
  planeToWorld3d,
} from "@simapp/contracts";

type Health = {
  status: string;
  contractVersion: string;
  milestone?: string;
  capabilities?: Record<string, unknown>;
};

type PrepareResult = {
  simulationReady?: boolean;
  prepareStatus?: string;
  validationStatus?: string;
  layoutRevision?: string;
  validationReport?: { status: string; checks: Array<{ ruleId: string; message: string }> };
};

const FX01_FACILITY = {
  contractVersion: "0.3",
  id: "facility-fx01",
  revision: "f-r1",
  parentRef: null,
  coord: { origin: "facility_sw_corner", xAxis: "east", yAxis: "north", unit: "m" },
  boundary: {
    outer: [
      { x: 0, y: 0 },
      { x: 40, y: 0 },
      { x: 40, y: 24 },
      { x: 0, y: 24 },
      { x: 0, y: 0 },
    ],
  },
  obstacles: [],
  openings: [
    {
      id: "door-recv",
      segment: [
        { x: 0, y: 10 },
        { x: 0, y: 14 },
      ],
      widthM: 4,
      heightM: 4.5,
      role: "recv",
      approachPolygon: null,
      evidence: {
        sourceKind: "demo",
        sourceRef: "FX-01",
        confirmationStatus: "confirmed",
        updatedAt: "2026-10-29T01:00:00+08:00",
      },
    },
    {
      id: "door-ship",
      segment: [
        { x: 40, y: 10 },
        { x: 40, y: 14 },
      ],
      widthM: 4,
      heightM: 4.5,
      role: "ship",
      approachPolygon: null,
      evidence: {
        sourceKind: "demo",
        sourceRef: "FX-01",
        confirmationStatus: "confirmed",
        updatedAt: "2026-10-29T01:00:00+08:00",
      },
    },
  ],
  reservedAreas: [],
  heightProfile: { kind: "uniform", heightM: 10 },
  evidence: {
    sourceKind: "demo",
    sourceRef: "FX-01",
    confirmationStatus: "confirmed",
    updatedAt: "2026-10-29T01:00:00+08:00",
  },
};

const FX01_LAYOUT = {
  contractVersion: "0.3",
  id: "layout-doc-fx01",
  revision: "ld-r1",
  facilityRef: { id: "facility-fx01", revision: "f-r1" },
  parentRef: null,
  elements: [
    {
      instanceId: "rack-001",
      typeElementId: "ST-PAL-01",
      pose: { x: 12, y: 14, yawDeg: 0 },
      params: { levels: 4, bays: 1, palletsPerBay: 2, minClearWidthM: 3.0 },
      assetDisposition: "new",
    },
    {
      instanceId: "dock-recv",
      typeElementId: "IN-DOCK-01",
      pose: { x: 1, y: 12, yawDeg: 0 },
      params: {},
      assetDisposition: "new",
    },
    {
      instanceId: "dock-ship",
      typeElementId: "OUT-DOCK-01",
      pose: { x: 39, y: 12, yawDeg: 180 },
      params: {},
      assetDisposition: "new",
    },
  ],
  aisles: [
    {
      id: "aisle-main",
      centerline: [
        { x: 2, y: 12 },
        { x: 38, y: 12 },
      ],
      widthM: 3.5,
    },
  ],
  locks: [],
  catalogVersion: "catalog-mvp@c-r1",
};

const FX01_DEMAND = {
  contractVersion: "0.3",
  id: "demand-fx01",
  revision: "d-r1",
  parentRef: null,
  goodsGroups: [
    {
      id: "gg-std-pallet",
      loadUnit: "pallet",
      dimensionsM: { length: 1.2, width: 1.0, height: 1.5 },
      grossWeightKg: 800,
      stackability: "stackable",
      allowedStorageTypes: ["ST-PAL-01", "ST-FLOOR-01"],
      quantityUnit: "pallet",
      evidence: {
        sourceKind: "demo",
        sourceRef: "FX-01",
        confirmationStatus: "confirmed",
        updatedAt: "2026-10-29T01:00:00+08:00",
      },
    },
  ],
  inventoryTargets: [{ goodsGroupId: "gg-std-pallet", quantity: 48, unit: "pallet" }],
  initialInventory: [],
  flows: [],
  arrivalProfile: { kind: "uniform", windowSec: 28800, unit: "pallet", paramsSource: "demo-fixture" },
  serviceTargets: [],
  assumptions: ["演示需求；非运营 KPI"],
  totalDemand: null,
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string>("");
  const [ready, setReady] = useState<PrepareResult | null>(null);

  const sample = planeToWorld3d({ x: 12, y: 14, yawDeg: 30 }, 1.5);

  async function pingApi() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/health");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setHealth((await res.json()) as Health);
    } catch (e) {
      setHealth(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runManualPrepare() {
    setBusy(true);
    setError(null);
    setReady(null);
    const lines: string[] = [];
    try {
      const pRes = await fetch("/api/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "M1 手动演示", unitSystem: "metric" }),
      });
      if (!pRes.ok) throw new Error(`create project ${pRes.status}`);
      const project = await pRes.json();
      lines.push(`项目 ${project.id}`);

      const fRes = await fetch(`/api/v1/projects/${project.id}/facility-revisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facility: FX01_FACILITY }),
      });
      if (!fRes.ok) throw new Error(`facility ${fRes.status}`);
      lines.push("场地 f-r1 已保存");

      const lRes = await fetch(`/api/v1/layouts/layout-doc-fx01/revisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: project.id,
          baseRevision: null,
          document: FX01_LAYOUT,
        }),
      });
      if (!lRes.ok) throw new Error(`layout ${lRes.status}: ${await lRes.text()}`);
      const saved = await lRes.json();
      lines.push(`布局修订 ${saved.layoutRef.revision}（保存≠可推演）`);

      const vRes = await fetch(`/api/v1/projects/${project.id}/variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "手动方案 A",
          source: "manual",
          layoutRef: saved.layoutRef,
        }),
      });
      if (!vRes.ok) throw new Error(`variant ${vRes.status}`);
      const variant = await vRes.json();
      lines.push(`方案 ${variant.id} source=manual`);

      const prepRes = await fetch(`/api/v1/layouts/layout-doc-fx01/prepare-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: project.id,
          layoutRef: saved.layoutRef,
          facilityRef: { id: "facility-fx01", revision: "f-r1" },
          ruleSetRefs: [{ id: "ruleset.m1.geometry", revision: "0.1" }],
          sync: true,
        }),
      });
      if (!prepRes.ok) throw new Error(`prepare ${prepRes.status}: ${await prepRes.text()}`);
      const prep = (await prepRes.json()) as PrepareResult & {
        simulationReady: boolean;
        prepareStatus: string;
        validationStatus: string;
      };
      setReady(prep);
      lines.push(
        `派生+校验 → prepareStatus=${prep.prepareStatus} simulationReady=${prep.simulationReady} validation=${prep.validationStatus}`,
      );
      setLog(lines.join("\n"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLog(lines.join("\n"));
    } finally {
      setBusy(false);
    }
  }

  async function runPlanningAdopt() {
    setBusy(true);
    setError(null);
    setReady(null);
    const lines: string[] = [];
    try {
      const pRes = await fetch("/api/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "M2 规划演示", unitSystem: "metric" }),
      });
      if (!pRes.ok) throw new Error(`create project ${pRes.status}`);
      const project = await pRes.json();
      lines.push(`项目 ${project.id}`);

      const fRes = await fetch(`/api/v1/projects/${project.id}/facility-revisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ facility: FX01_FACILITY }),
      });
      if (!fRes.ok) throw new Error(`facility ${fRes.status}`);
      const gate = (await fRes.json()).gate;
      lines.push(
        `场地确认 gate.usableForValidatedPlanning=${gate?.usableForValidatedPlanning}`,
      );

      await fetch("/api/v1/demands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId: project.id, demand: FX01_DEMAND }),
      });

      const empty = {
        contractVersion: "0.3",
        id: "layout-empty-ui",
        revision: "ld-e1",
        facilityRef: { id: "facility-fx01", revision: "f-r1" },
        parentRef: null,
        elements: [],
        aisles: [],
        locks: [],
        catalogVersion: "catalog-mvp@c-r1",
      };
      await fetch("/api/v1/layouts/layout-empty-ui/revisions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId: project.id, baseRevision: null, document: empty }),
      });
      const vRes = await fetch(`/api/v1/projects/${project.id}/variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "底稿",
          source: "manual",
          layoutRef: { id: "layout-empty-ui", revision: "ld-e1" },
        }),
      });
      const variant = await vRes.json();
      lines.push(`底稿方案 ${variant.id}@${variant.revision}`);

      const draftRes = await fetch(`/api/v1/projects/${project.id}/planning-drafts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request: {
            contractVersion: "0.3",
            goals: ["capacity", "efficiency"],
            evaluationLevel: "quick",
          },
        }),
      });
      const draft = await draftRes.json();
      lines.push(
        `向导草稿 ${draft.id}；禁用目标: ${(draft.disabledGoals || [])
          .map((g: { goal: string; reason: string }) => `${g.goal}(${g.reason})`)
          .join("; ") || "无"}`,
      );

      const planRes = await fetch("/api/v1/planning-jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contractVersion: "0.3",
          projectId: project.id,
          facilityRef: { id: "facility-fx01", revision: "f-r1" },
          baseVariantRef: { id: variant.id, revision: variant.revision },
          demandRef: { id: "demand-fx01", revision: "d-r1" },
          scope: { mode: "whole" },
          locks: [],
          goals: ["capacity"],
          constraints: { allowedTypeIds: ["ST-PAL-01", "IN-DOCK-01", "OUT-DOCK-01"] },
          evaluationLevel: "quick",
          budget: {
            maxConfigurations: 50,
            maxIterations: 1000,
            maxWallTimeSec: 30,
            maxMemoryMb: 512,
          },
          seed: 42,
          catalogRef: { id: "catalog-mvp", revision: "c-r1" },
          templateSetRef: { id: "template-rect", revision: "t-r1" },
          ruleSetRefs: [],
        }),
      });
      if (!planRes.ok) throw new Error(`planning ${planRes.status}: ${await planRes.text()}`);
      const plan = await planRes.json();
      lines.push(
        `PlanningJob ${plan.jobId} outcome=${plan.outcome} candidates=${plan.candidates?.length ?? 0}`,
      );
      lines.push("※ quick 几何容量/路径估算 ≠ 运营效率验证（M3）");

      const cand = plan.candidates?.[0];
      if (!cand) throw new Error("no candidate");
      const adoptRes = await fetch(`/api/v1/candidates/${cand.id}/adoptions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: project.id,
          currentVariantRef: { id: variant.id, revision: variant.revision },
          newName: "生成方案 A",
          expectedVariantRevision: variant.revision,
        }),
      });
      if (!adoptRes.ok) throw new Error(`adopt ${adoptRes.status}: ${await adoptRes.text()}`);
      const adopted = await adoptRes.json();
      lines.push(
        `采用 → 新方案 ${adopted.variant.id} layout=${adopted.layoutRef.id}@${adopted.layoutRef.revision}（原底稿未覆盖）`,
      );
      setLog(lines.join("\n"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLog(lines.join("\n"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <h1 className="brand">simapp</h1>
      <p className="lead">
        仓库布局规划与运营推演 · M2 可选自动规划（DEC-05）。外层契约 {CONTRACT_VERSION}；Snapshot /
        equip {SNAPSHOT_SCHEMA_VERSION} / {EQUIP_SCHEMA_VERSION}。手动路径独立；quick
        评估不宣称运营效率。
      </p>
      <div className="cta">
        <button type="button" onClick={pingApi} disabled={busy}>
          {busy ? "请求中…" : "探测 API /health"}
        </button>
        <button type="button" onClick={runManualPrepare} disabled={busy}>
          手动路径：保存并推演准备
        </button>
        <button type="button" onClick={runPlanningAdopt} disabled={busy}>
          可选规划：生成并采用分支
        </button>
        <a className="note" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
          OpenAPI docs
        </a>
      </div>
      <section className="panel">
        <dl className="meta">
          <dt>milestone</dt>
          <dd>M2 · DEV-06–09</dd>
          <dt>planning</dt>
          <dd>ST-PAL-01 真实设备候选；锁定不变；乐观锁不覆盖</dd>
          <dt>3D map sample</dt>
          <dd>
            (12,14,yaw30) @1.5m → ({sample.position.x}, {sample.position.y}, {sample.position.z}),
            yawY={sample.yawYDeg}°
          </dd>
        </dl>
        {error ? <p className="note">错误：{error}</p> : null}
        {health ? <pre>{JSON.stringify(health, null, 2)}</pre> : null}
        {log ? <pre>{log}</pre> : null}
        {ready ? (
          <pre>
            {JSON.stringify(
              {
                simulationReady: ready.simulationReady,
                prepareStatus: ready.prepareStatus,
                validationStatus: ready.validationStatus,
                layoutRevision: ready.layoutRevision,
                failingChecks: ready.validationReport?.checks?.filter((c) => c.ruleId),
              },
              null,
              2,
            )}
          </pre>
        ) : null}
        <p className="note">
          夹具：<code>npm run validate:fixtures</code> · M1：<code>npm run test:m1</code> · M2：
          <code>npm run test:m2</code>
        </p>
      </section>
    </main>
  );
}
