import { useState, type ReactNode } from "react";
import { copy } from "../copy";
import { cardDeltaText, formatP95, formatRate, formatThroughput, formatWait, pinCards, runReport, unitAmount } from "./format.js";

type CardPin = {
  layoutRevision: string;
  throughput: number | null;
  waitMeanSec: number | null;
  waitP95Sec: number | null;
  forkliftCount: number | null;
  bottleneckId: string;
};

type UtilRow = { resourceType?: string; resourceId?: string; utilization?: number | null; resourceCount?: number };
type Bottle = { entityId?: string; waitSec?: number; share?: number };

type Props = {
  run: Record<string, unknown> | null;
  stale: string | null;
  rejected: string | null;
  idleNotice: string | null;
  summary: string;
  simT: number;
  t0: number;
  t1: number;
  playing: boolean;
  onSimT: (value: number) => void;
  onTogglePlay: () => void;
  onBack: () => void;
  pinned?: CardPin | null;
  onPin?: () => void;
  unitPrice?: number | null;
  children: ReactNode;
};

export function RunCards({
  run,
  stale,
  rejected,
  idleNotice,
  summary,
  simT,
  t0,
  t1,
  playing,
  onSimT,
  onTogglePlay,
  onBack,
  pinned,
  onPin,
  unitPrice,
  children,
}: Props) {
  const cards = (run?.cards ?? null) as Record<string, unknown> | null;
  const throughput = cards?.throughput as { value?: number | null } | undefined;
  const wait = cards?.wait as { meanSec?: number | null; p95Sec?: number | null; sampleCount?: number } | undefined;
  const util = cards?.utilization as { byResourceType?: UtilRow[]; byResource?: UtilRow[] } | undefined;
  const bottle = cards?.bottleneck as { topN?: Bottle[] } | undefined;
  const secondary = run?.secondary as { completionRate?: number | null; completedTasks?: number; incompleteTasks?: number } | undefined;
  const top = bottle?.topN ?? [];
  const manifest = run?.runManifest as { engineVersion?: string; seedStreams?: Record<string, number> } | undefined;
  const showCards = Boolean(run) && !rejected;
  const conveyor = (run?.secondary as { conveyor?: { segments?: Array<{ instanceId?: string; occupancy?: number | null }>; handoffQueueSec?: number } } | undefined)
    ?.conveyor;
  const replaySegments = ((run?.trajectory as { segments?: Array<{ mode?: string }> } | undefined)?.segments ?? []);
  const hasConveyorReplay = replaySegments.some((segment) => segment.mode === "conveyor");
  const banner = rejected || (showCards ? null : idleNotice || copy.notRun);
  const bannerClass = rejected || (banner && banner.startsWith(copy.unsimulated)) ? "rejected" : "decision-idle";
  const [report, setReport] = useState("");
  const currentPin = run && showCards ? pinCards(run) : null;
  const forkliftCount = currentPin?.forkliftCount ?? null;
  const amount = showCards && forkliftCount !== null ? unitAmount(forkliftCount, unitPrice ?? null) : null;
  const delta = showCards && pinned && currentPin ? cardDeltaText(pinned, currentPin) : "";
  function onReport() {
    if (!run || !showCards) return;
    const text = runReport(run);
    setReport(text);
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "run-report.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section className="decision" id="decisionView" data-decision-cards={showCards ? "shown" : "hidden"}>
      <div className="decision-top">
        <div>
          <h1>综合仓 · 运营决策</h1>
          <div className="decision-summary">{summary}</div>
        </div>
        <div className="decision-actions">
          <button className="ghost-btn" type="button" onClick={onBack}>
            返回编辑
          </button>
          <button
            className="ghost-btn"
            type="button"
            id="runReport"
            data-run-report={showCards ? "ready" : "idle"}
            disabled={!showCards}
            title={showCards ? "转写这一次运行的四卡" : copy.report}
            onClick={onReport}
          >
            仿真报告
          </button>
          <button className="ghost-btn" id="pinCards" type="button" disabled={!showCards} onClick={onPin}>
            记下这组四卡
          </button>
          <button className="ghost-btn" type="button" disabled title="本切片不导出设备清单">
            设备清单
          </button>
          <button className="ghost-btn" type="button" disabled title="本切片不导出 CAD">
            导出 CAD
          </button>
        </div>
      </div>
      {banner ? <div className={bannerClass}>{banner}</div> : null}
      {showCards && stale ? <div className="stale-banner">{stale}</div> : null}
      {showCards && report ? (
        <pre className="run-report" id="runReportText">
          {report}
        </pre>
      ) : null}
      {amount?.ok ? <p id="runUnitAmount">{amount.text}</p> : null}
      {delta ? (
        <pre className="card-delta" id="cardDelta">
          {delta}
        </pre>
      ) : null}
      {showCards ? <div className="kpis">
        <article className="kpi">
          <div className="kpi-label">{copy.cards.throughput}</div>
          <div className="kpi-value">
            <span>{run && !rejected ? formatThroughput(throughput?.value ?? null) : "—"}</span>
            <span className="unit">{copy.units.throughput}</span>
          </div>
          <div className="kpi-foot">外部发运托当量 / 评价时长</div>
        </article>
        <article className="kpi">
          <div className="kpi-label">{copy.cards.wait}</div>
          <div className="kpi-value">
            <span>{run && !rejected ? formatWait(wait?.meanSec ?? null) : "—"}</span>
            <span className="unit">{copy.units.wait}</span>
          </div>
          <div className="kpi-foot">
            P95 {run && !rejected ? formatP95(wait?.p95Sec ?? null) : "—"} · 样本 {wait?.sampleCount ?? "—"}
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-label">{copy.cards.utilization}</div>
          <div className="util-lines">
            {run && !rejected && util?.byResourceType?.length
              ? util.byResourceType.map((row) => (
                  <div key={row.resourceType}>
                    {row.resourceType} {formatRate(row.utilization ?? null)}
                  </div>
                ))
              : "—"}
          </div>
          <div className="kpi-foot">
            {(util?.byResource ?? []).map((row) => `${row.resourceId} ${formatRate(row.utilization ?? null)}`).join(" · ") ||
              "按资源类型分列"}
          </div>
        </article>
        <article className="kpi">
          <div className="kpi-label">{copy.cards.bottleneck}</div>
          <div className="kpi-value" style={{ fontSize: 21, paddingTop: 5 }}>
            {run && !rejected ? (top[0]?.entityId ?? copy.noWaitSample) : "—"}
          </div>
          <div className="kpi-foot">
            {top[0] ? `等待 ${formatWait(top[0].waitSec ?? null)} 秒 · ${formatRate(top[0].share ?? null)}` : copy.noWaitSample}
          </div>
        </article>
      </div> : null}
      {showCards ? <div className="decision-body">
        <div className="replay">
          <div className="replay-head">
            <strong>动线回放</strong>
            <span style={{ fontSize: 11, color: "#8aa09c" }}>
              按本次 trajectory.segments 插值{hasConveyorReplay ? `。${copy.conveyorReplay}` : ""}
            </span>
          </div>
          <div className="replay-board">{children}</div>
          <div className="replay-controls">
            <button type="button" onClick={onTogglePlay} aria-label="暂停或播放">
              {playing ? "暂停" : "播放"}
            </button>
            <span>{clockSeconds(simT)}</span>
            <input
              type="range"
              min={0}
              max={1000}
              value={sliderValue(simT, t0, t1)}
              aria-label="回放进度"
              onChange={(event) => onSimT(t0 + (Number(event.target.value) / 1000) * Math.max(t1 - t0, 0))}
            />
            <span>完成率 {run && !rejected ? formatRate(secondary?.completionRate ?? null) : copy.rateNa}</span>
          </div>
        </div>
        <div className="decision-side">
          <div className="panel-section">
            <div className="panel-row">
              <h3>瓶颈 TopN</h3>
              <span className="mini-tag amber">等待贡献</span>
            </div>
            {top.length === 0 ? (
              <div className="not-run">{copy.noWaitSample}</div>
            ) : (
              top.map((row, index) => (
                <div className="bottleneck" key={row.entityId ?? index}>
                  <span className="rank">{index + 1}</span>
                  <span className="bottle-copy">
                    <strong>{row.entityId}</strong>
                    <span>{formatWait(row.waitSec ?? null)} 秒</span>
                  </span>
                  <span className="bottle-share">{formatRate(row.share ?? null)}</span>
                </div>
              ))
            )}
          </div>
          {conveyor ? (
            <div className="panel-section">
              <div className="panel-row">
                <h3>输送段占用</h3>
                <span className="mini-tag">不进主四卡</span>
              </div>
              {(conveyor.segments ?? []).map((row) => (
                <div className="delta" key={row.instanceId}>
                  <span>{row.instanceId}</span>
                  <b>{formatRate(row.occupancy ?? null)}</b>
                </div>
              ))}
              <div className="delta">
                <span>接驳口排队</span>
                <b>{formatWait(conveyor.handoffQueueSec ?? 0)} 秒</b>
              </div>
            </div>
          ) : null}
          <div className="panel-section">
            <div className="panel-row">
              <h3>运行信息</h3>
            </div>
            <div className="delta">
              <span>布局修订</span>
              <b>{String(run?.layoutRevision ?? copy.notIssued)}</b>
            </div>
            <div className="delta">
              <span>引擎</span>
              <b>{manifest?.engineVersion ?? "—"}</b>
            </div>
            <div className="delta">
              <span>种子</span>
              <b>{manifest?.seedStreams ? JSON.stringify(manifest.seedStreams) : "—"}</b>
            </div>
            <div className="delta">
              <span>完成 / 未完成</span>
              <b>
                {secondary ? `${secondary.completedTasks ?? 0} / ${secondary.incompleteTasks ?? 0}` : "—"}
              </b>
            </div>
          </div>
        </div>
      </div> : null}
    </section>
  );
}

function clockSeconds(secIn: number) {
  const sec = Math.max(0, Math.round(secIn));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function sliderValue(simT: number, t0: number, t1: number) {
  const span = t1 - t0;
  if (span <= 0) return 0;
  return Math.round(Math.min(1, Math.max(0, (simT - t0) / span)) * 1000);
}
