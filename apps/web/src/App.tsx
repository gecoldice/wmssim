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
  snapshotSchemaVersion?: string;
  equipSchemaVersion?: string;
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <main className="shell">
      <h1 className="brand">simapp</h1>
      <p className="lead">
        仓库布局规划与运营推演 · M0 契约与夹具脚手架。外层契约 {CONTRACT_VERSION}；
        Snapshot / equip 仍为 {SNAPSHOT_SCHEMA_VERSION} / {EQUIP_SCHEMA_VERSION}。
        计算层不引入 UI 演示 KPI。
      </p>
      <div className="cta">
        <button type="button" onClick={pingApi} disabled={busy}>
          {busy ? "请求中…" : "探测 API /health"}
        </button>
        <a className="note" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
          OpenAPI docs
        </a>
      </div>
      <section className="panel">
        <dl className="meta">
          <dt>contract</dt>
          <dd>{CONTRACT_VERSION}</dd>
          <dt>snapshot / equip</dt>
          <dd>
            {SNAPSHOT_SCHEMA_VERSION} / {EQUIP_SCHEMA_VERSION}
          </dd>
          <dt>3D map sample</dt>
          <dd>
            (12,14,yaw30) @1.5m → ({sample.position.x}, {sample.position.y},{" "}
            {sample.position.z}), yawY={sample.yawYDeg}°
          </dd>
        </dl>
        {error ? <p className="note">API 未就绪：{error}（先启动 FastAPI）</p> : null}
        {health ? <pre>{JSON.stringify(health, null, 2)}</pre> : null}
        <p className="note">
          校验夹具：<code>PYTHONPATH=shared/python python3 scripts/validate_fixtures.py</code>
        </p>
      </section>
    </main>
  );
}
