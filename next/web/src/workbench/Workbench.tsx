import { useEffect, useRef, useState } from "react";
import {
  createProject,
  getFacility,
  getLayout,
  getProject,
  getRun,
  pollJob,
  saveFacility,
  saveLayout,
  startPrepare,
  startSimulation,
} from "../api/client";
import { LayoutCanvas } from "../canvas/LayoutCanvas";
import { copy } from "../copy";
import { InspectorPanel } from "../inspector/InspectorPanel";
import { LibraryPanel } from "../library/LibraryPanel";
import type { CatalogGroup } from "../library/catalog";
import { readAccepted, rememberAccepted } from "../persist/lastAccepted.js";
import { PreparePanel } from "../prepare/PreparePanel";
import { acceptRun, staleMessage } from "../run-cards/format.js";
import { positionAt, routesFromSnapshot, type Segment } from "../run-cards/playback";
import { RunCards } from "../run-cards/RunCards";
import {
  buildDemand,
  buildFacility,
  buildLayout,
  buildOperating,
  draftFor,
  emptyScenario,
  horizonSec,
  missingScenario,
  nextInstance,
  parseNum,
  scenarioKey,
  testScenario,
  type Draft,
  type PlaceableType,
  type ScenarioFields,
} from "./draft";

type Check = { status?: string; message?: string; objectIds?: string[]; ruleId?: string };
type Bound = { layoutRevision: string; outbound: string; scenarioKey: string };

function textOf(data: Record<string, unknown> | undefined): string {
  if (!data) return "请求失败";
  return String(data.message || data.code || "请求失败");
}

function draftFromSaved(facility: Record<string, unknown>, document: Record<string, unknown>): Draft {
  const outer = ((facility.boundary as { outer?: Array<{ x: number; y: number }> })?.outer) ?? [];
  const width = outer.reduce((max, point) => Math.max(max, point.x), 0);
  const height = outer.reduce((max, point) => Math.max(max, point.y), 0);
  const aisle = ((document.aisles as Array<Record<string, unknown>>) ?? [])[0];
  const line = (aisle?.centerline as Array<{ x: number; y: number }>) ?? [];
  const allowed = new Set(["ST-PAL-01", "IN-DOCK-01", "OUT-DOCK-01"]);
  const elements = ((document.elements as Array<Record<string, unknown>>) ?? [])
    .filter((el) => allowed.has(String(el.typeElementId)))
    .map((el) => {
      const pose = el.pose as { x: number; y: number; yawDeg?: number };
      return {
        instanceId: String(el.instanceId),
        typeElementId: el.typeElementId as PlaceableType,
        x: pose.x,
        y: pose.y,
        yawDeg: pose.yawDeg ?? 0,
      };
    });
  return {
    widthM: String(width),
    heightM: String(height),
    aisleWidthM: aisle?.widthM === undefined ? "" : String(aisle.widthM),
    aisleFromX: line[0] ? String(line[0].x) : "",
    aisleToX: line.length ? String(line[line.length - 1].x) : "",
    aisleY: line[0] ? String(line[0].y) : "",
    elements,
  };
}

export function Workbench() {
  const [mode, setMode] = useState<"edit" | "decision">("edit");
  const [started, setStarted] = useState(false);
  const [draft, setDraft] = useState<Draft>(draftFor("blank"));
  const [past, setPast] = useState<Draft[]>([]);
  const [future, setFuture] = useState<Draft[]>([]);
  const [scenario, setScenario] = useState<ScenarioFields>(emptyScenario());
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  const [facilityId, setFacilityId] = useState("facility-main");
  const [facilityRev, setFacilityRev] = useState<string | null>(null);
  const [layoutId, setLayoutId] = useState("");
  const [layoutRev, setLayoutRev] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | CatalogGroup>("all");
  const [prepare, setPrepare] = useState<{ ready: boolean; checks: Check[]; snapshot: Record<string, unknown> | null } | null>(null);
  const [run, setRun] = useState<Record<string, unknown> | null>(null);
  const [bound, setBound] = useState<Bound | null>(null);
  const [rejected, setRejected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [showGrid, setShowGrid] = useState(true);
  const [showRoute, setShowRoute] = useState(true);
  const [testValues, setTestValues] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const dragOrigin = useRef<Draft | null>(null);

  const dirty = JSON.stringify(draft) !== savedKey;
  const selectedEl = draft.elements.find((el) => el.instanceId === selected) ?? null;

  function note(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 2600);
  }

  function replaceDraft(next: Draft, recordHistory: boolean) {
    if (recordHistory) {
      setPast((items) => [...items, structuredClone(draft)].slice(-30));
      setFuture([]);
    }
    setDraft(next);
    setPrepare(null);
  }

  useEffect(() => {
    const accepted = readAccepted(localStorage);
    if (!accepted) return;
    let cancel = false;
    void (async () => {
      const project = await getProject(accepted.projectId);
      const facility = await getFacility(accepted.projectId);
      const layout = await getLayout(accepted.layoutId);
      if (cancel || layout.status !== 200 || facility.status !== 200 || project.status !== 200) return;
      const projectBody = project.data.project as { name?: string };
      const facilityBody = facility.data.facility as Record<string, unknown>;
      const facilityRef = facility.data.facilityRef as { id: string; revision: string };
      const document = layout.data.document as Record<string, unknown>;
      const layoutRef = layout.data.layoutRef as { revision: string };
      const next = draftFromSaved(facilityBody, document);
      setProjectId(accepted.projectId);
      setProjectName(projectBody.name ?? "");
      setFacilityId(facilityRef.id);
      setFacilityRev(facilityRef.revision);
      setLayoutId(accepted.layoutId);
      setLayoutRev(layoutRef.revision);
      setDraft(next);
      setSavedKey(JSON.stringify(next));
      setStarted(true);
    })();
    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    if (!playing || mode !== "decision") return;
    let handle = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setPlayhead((value) => (value + dt / 20) % 1);
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [playing, mode]);

  function choose(kind: "blank" | "rectangle") {
    setDraft(draftFor(kind));
    setPast([]);
    setFuture([]);
    setSavedKey(null);
    setStarted(true);
    setPrepare(null);
  }

  function undo() {
    setPast((items) => {
      if (!items.length) return items;
      const previous = items[items.length - 1];
      setFuture((queue) => [draft, ...queue]);
      setDraft(previous);
      setPrepare(null);
      return items.slice(0, -1);
    });
  }

  function redo() {
    setFuture((items) => {
      if (!items.length) return items;
      const next = items[0];
      setPast((queue) => [...queue, draft]);
      setDraft(next);
      setPrepare(null);
      return items.slice(1);
    });
  }

  async function onSave() {
    setBusy(true);
    try {
      let pid = projectId;
      let lid = layoutId;
      if (!pid) {
        const created = await createProject(projectName.trim() || "未命名综合仓");
        if (created.status !== 201) throw new Error(textOf(created.data));
        pid = String(created.data.id);
        lid = `layout-${crypto.randomUUID()}`;
        setProjectId(pid);
        setLayoutId(lid);
      }
      if (!lid) {
        lid = `layout-${crypto.randomUUID()}`;
        setLayoutId(lid);
      }
      const facility = buildFacility(draft, facilityId, facilityRev ?? "pending");
      const savedFacility = await saveFacility(pid, facility, facilityRev);
      if (savedFacility.status !== 201) throw new Error(textOf(savedFacility.data));
      const facilityRef = savedFacility.data.facilityRef as { id: string; revision: string };
      setFacilityId(facilityRef.id);
      setFacilityRev(facilityRef.revision);
      const document = buildLayout(draft, lid, layoutRev ?? "pending", facilityRef);
      const saved = await saveLayout(lid, pid, layoutRev, document);
      if (saved.status !== 201) throw new Error(textOf(saved.data));
      const layoutRef = saved.data.layoutRef as { revision: string };
      setLayoutRev(layoutRef.revision);
      setSavedKey(JSON.stringify(draft));
      setPrepare(null);
      rememberAccepted(localStorage, { projectId: pid, layoutId: lid });
      note(copy.saved);
    } catch (error) {
      note(`${copy.saveFailed} ${error instanceof Error ? error.message : ""}`);
    } finally {
      setBusy(false);
    }
  }

  async function onPrepare() {
    if (!layoutRev || dirty || !projectId) {
      note(copy.needSave);
      return;
    }
    setBusy(true);
    try {
      const startedJob = await startPrepare(layoutId, layoutRev);
      if (startedJob.status !== 202) throw new Error(textOf(startedJob.data));
      const job = await pollJob(String(startedJob.data.jobId));
      if (job.data.status === "failed") throw new Error(textOf(job.data.error as Record<string, unknown>));
      const result = job.data.result as {
        simulationReady?: boolean;
        validationReport?: { checks?: Check[] };
        snapshot?: Record<string, unknown>;
      };
      const checks = result.validationReport?.checks ?? [];
      setPrepare({ ready: Boolean(result.simulationReady), checks, snapshot: result.snapshot ?? null });
      note(result.simulationReady ? "准备通过，可以推演" : copy.validationFail);
    } catch (error) {
      note(`${copy.validationFail} ${error instanceof Error ? error.message : ""}`);
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    if (!layoutRev || !prepare?.ready || dirty) {
      note(copy.needPrepare);
      return;
    }
    const missing = missingScenario(scenario);
    if (missing.length) {
      note(`${copy.needFields} ${missing.join("、")}`);
      return;
    }
    setBusy(true);
    setRejected(null);
    try {
      const body = {
        layoutRef: { id: layoutId, revision: layoutRev },
        demand: buildDemand(draft, scenario),
        operating: buildOperating(scenario),
        runControl: {
          horizonSec: horizonSec(scenario),
          seedStreams: { demand: 7 },
          metricDefinitionVersion: "metrics-slice-manual-v1",
        },
      };
      const startedJob = await startSimulation(body);
      if (startedJob.status !== 202) throw new Error(textOf(startedJob.data));
      const job = await pollJob(String(startedJob.data.jobId));
      if (job.data.status !== "succeeded") {
        const error = job.data.error as Record<string, unknown> | undefined;
        throw new Error(textOf(error ?? job.data));
      }
      const result = job.data.result as { runId?: string };
      const fetched = await getRun(String(result.runId));
      if (fetched.status !== 200) throw new Error(textOf(fetched.data));
      const accepted = acceptRun(fetched.data);
      if (!accepted.ok) {
        setRun(null);
        setRejected(accepted.error ?? copy.demoRejected);
        setMode("decision");
        return;
      }
      setRun(accepted.run as Record<string, unknown>);
      setBound({ layoutRevision: layoutRev, outbound: scenario.outbound, scenarioKey: scenarioKey(scenario) });
      setPlayhead(0);
      setMode("decision");
      note("推演完成");
    } catch (error) {
      setRun(null);
      setRejected(`${copy.simFail} ${error instanceof Error ? error.message : ""}`);
      setMode("decision");
    } finally {
      setBusy(false);
    }
  }

  const layoutChanged = Boolean(run && bound && layoutRev && bound.layoutRevision !== layoutRev);
  const demandChanged = Boolean(run && bound && bound.outbound !== scenario.outbound);
  const scenarioChanged = Boolean(run && bound && bound.scenarioKey !== scenarioKey(scenario));
  const stale = run ? staleMessage({ layoutChanged, demandChanged, scenarioChanged }) : null;
  const conflictIds = (prepare?.checks ?? [])
    .filter((check) => check.status === "fail")
    .flatMap((check) => check.objectIds ?? [])
    .filter((id) => draft.elements.some((el) => el.instanceId === id));
  const routes = routesFromSnapshot(prepare?.snapshot ?? null);
  const segments = ((run?.trajectory as { segments?: Segment[] } | undefined)?.segments) ?? [];
  const horizon = Number((run?.trajectory as { horizonSec?: number } | undefined)?.horizonSec ?? 0);
  const marker = run ? positionAt(segments, playhead * horizon) : null;
  const statusText = conflictIds.length ? "硬冲突" : dirty || !layoutRev ? "未保存" : prepare?.ready ? "可推演" : prepare ? "准备未通过" : "未准备";
  const statusClass = conflictIds.length || (prepare && !prepare.ready) ? "status-pill error" : statusText === "可推演" ? "status-pill" : "status-pill warn";
  const widthLabel = draft.widthM && draft.heightM ? `${draft.widthM} × ${draft.heightM} m` : copy.missing;

  const canvas = (
    <LayoutCanvas
      draft={draft}
      selected={selected}
      pending={pending}
      conflictIds={conflictIds}
      showGrid={showGrid}
      showRoute={showRoute}
      routes={routes}
      marker={mode === "decision" ? marker : null}
      badge={stale ? stale : layoutRev ? `修订 ${layoutRev}` : "尚未保存"}
      interactive={mode === "edit"}
      onPlace={(x, y) => {
        if (!pending) return;
        const type = pending as PlaceableType;
        const width = parseNum(draft.widthM);
        const height = parseNum(draft.heightM);
        if (width === null || height === null || x < 0 || y < 0 || x > width || y > height) {
          note("放置无效：请先填写场地，并放在场地内");
          return;
        }
        const element = {
          instanceId: nextInstance(draft.elements, type),
          typeElementId: type,
          x: Math.round(x * 10) / 10,
          y: Math.round(y * 10) / 10,
          yawDeg: type === "OUT-DOCK-01" ? 180 : 0,
        };
        replaceDraft({ ...draft, elements: [...draft.elements, element] }, true);
        setSelected(element.instanceId);
        setPending(null);
      }}
      onSelect={setSelected}
      onMove={(id, x, y, phase) => {
        if (phase === "start") {
          dragOrigin.current = structuredClone(draft);
          return;
        }
        const width = parseNum(draft.widthM);
        const height = parseNum(draft.heightM);
        if (phase === "end" && width !== null && height !== null && (x < 0 || y < 0 || x > width || y > height)) {
          if (dragOrigin.current) setDraft(dragOrigin.current);
          note("位置无效：已恢复到场地内");
          return;
        }
        setDraft((current) => ({
          ...current,
          elements: current.elements.map((el) => (el.instanceId === id ? { ...el, x, y } : el)),
        }));
        if (phase === "end" && dragOrigin.current) {
          setPast((items) => [...items, dragOrigin.current as Draft].slice(-30));
          setFuture([]);
          setPrepare(null);
        }
      }}
    />
  );

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brandmark">
            <b />
            <b />
            <b />
            <b />
          </span>
          <span className="brandname">
            仓序<span style={{ color: "#9baaaa", fontWeight: 400 }}> / </span>规划
          </span>
        </div>
        <div className="project">
          <span className="slash">/</span>
          <input
            className="project-title-input"
            aria-label="项目名称"
            placeholder="未命名综合仓"
            value={projectName}
            onChange={(event) => setProjectName(event.target.value)}
          />
          <span className="topmeta">{started ? "人工摆放" : "选择起步"}</span>
        </div>
        <div className="mode-switch">
          <button type="button" className={mode === "edit" ? "active" : ""} onClick={() => setMode("edit")}>
            布局编辑
          </button>
          <button type="button" className={mode === "decision" ? "active" : ""} onClick={() => setMode("decision")}>
            决策视图
          </button>
        </div>
        <div className="top-actions">
          <span className="save-state">
            <span className="dot" />
            <span>{layoutRev && !dirty ? copy.saved : copy.unsaved}</span>
          </span>
          <button className="icon-btn" type="button" onClick={undo} disabled={!past.length} aria-label="撤销">
            ↩
          </button>
          <button className="icon-btn" type="button" onClick={redo} disabled={!future.length} aria-label="重做">
            ↪
          </button>
          <button className="icon-btn" type="button" onClick={() => void onSave()} disabled={busy} aria-label="保存布局">
            存
          </button>
        </div>
      </header>
      {mode === "edit" ? (
        <div className="workspace" id="workspace">
          <LibraryPanel
            pending={pending}
            query={query}
            filter={filter}
            onQuery={setQuery}
            onFilter={setFilter}
            onPick={(id, placeable) => {
              if (!placeable) {
                note(copy.unsupportedType);
                return;
              }
              setPending((current) => (current === id ? null : id));
            }}
          />
          <main className="main" id="editorMain">
            <div className="canvas-head">
              <div>
                <div className="canvas-title">综合仓布局</div>
                <div className="canvas-caption">设备与通道 / {widthLabel}</div>
              </div>
              <div className="canvas-tools">
                <div className="view-switch">
                  <button type="button" className="active">
                    2D 顶视
                  </button>
                  <button type="button" onClick={() => note(copy.view3d)}>
                    3D 巡视
                  </button>
                </div>
                <button className="icon-btn" type="button" onClick={() => setShowGrid((value) => !value)} aria-label="切换网格">
                  格
                </button>
                <button className="icon-btn" type="button" onClick={() => setShowRoute((value) => !value)} aria-label="切换动线">
                  线
                </button>
                <button className="ghost-btn" type="button" onClick={() => choose("blank")}>
                  空白场地
                </button>
                <button className="ghost-btn" type="button" onClick={() => choose("rectangle")}>
                  矩形模板
                </button>
              </div>
            </div>
            {started ? (
              canvas
            ) : (
              <div className="board-wrap">
                <div className="board-frame">
                  <div className="start-choices">
                    <p>{copy.emptyLayout}</p>
                    <button className="ghost-btn" type="button" onClick={() => choose("blank")}>
                      空白场地
                    </button>
                    <button className="run-btn" type="button" style={{ width: 180 }} onClick={() => choose("rectangle")}>
                      矩形模板
                    </button>
                  </div>
                </div>
              </div>
            )}
            <div className="bottom-strip">
              <span className={statusClass}>{statusText}</span>
              <span className="stat">
                设备 <strong>{draft.elements.length}</strong>
              </span>
              <span className="stat">
                货架 <strong>{draft.elements.filter((el) => el.typeElementId === "ST-PAL-01").length}</strong>
              </span>
              <span className="stat">
                硬冲突 <strong>{conflictIds.length}</strong>
              </span>
              <span className="stat">
                布局修订 <strong>{layoutRev ?? copy.notIssued}</strong>
              </span>
            </div>
          </main>
          <aside className="inspector" id="inspectorPanel">
            <InspectorPanel
              draft={draft}
              onDraft={(patch) => replaceDraft({ ...draft, ...patch }, true)}
              selectedCaption={selectedEl ? `${selectedEl.typeElementId} · ${selectedEl.instanceId}` : "当前未选中设备"}
              selectedId={selectedEl?.instanceId ?? null}
              selectedType={selectedEl?.typeElementId ?? null}
              x={selectedEl ? String(selectedEl.x) : ""}
              y={selectedEl ? String(selectedEl.y) : ""}
              onPose={(axis, value) => {
                const number = parseNum(value);
                if (!selectedEl || number === null) return;
                replaceDraft(
                  {
                    ...draft,
                    elements: draft.elements.map((el) => (el.instanceId === selectedEl.instanceId ? { ...el, [axis]: number } : el)),
                  },
                  true,
                );
              }}
              fields={scenario}
              onField={(patch) => setScenario((current) => ({ ...current, ...patch }))}
              onTestValues={() => {
                setScenario(testScenario());
                setTestValues(true);
              }}
              testValues={testValues}
              checks={prepare?.checks ?? []}
              prepareReady={prepare ? prepare.ready : null}
              onRecheck={() => void onPrepare()}
            />
            <PreparePanel
              busy={busy}
              canDelete={Boolean(selectedEl)}
              runLabel={run ? "再次推演" : "开始推演"}
              onPrepare={() => void onPrepare()}
              onDelete={() => {
                if (!selected) return;
                replaceDraft({ ...draft, elements: draft.elements.filter((el) => el.instanceId !== selected) }, true);
                setSelected(null);
              }}
              onRun={() => void onRun()}
            />
          </aside>
        </div>
      ) : (
        <RunCards
          run={run}
          stale={stale}
          rejected={rejected}
          summary={`${projectName || "未命名综合仓"} · 修订 ${run?.layoutRevision ?? copy.notIssued}`}
          playhead={playhead}
          playing={playing}
          onPlayhead={setPlayhead}
          onTogglePlay={() => setPlaying((value) => !value)}
          onBack={() => setMode("edit")}
        >
          {canvas}
        </RunCards>
      )}
      <nav className="mobile-nav">
        <button type="button" onClick={() => { setMode("edit"); document.getElementById("libraryPanel")?.scrollIntoView(); }}>
          元素
        </button>
        <button type="button" onClick={() => { setMode("edit"); document.getElementById("editorMain")?.scrollIntoView(); }}>
          画布
        </button>
        <button type="button" onClick={() => { setMode("edit"); document.getElementById("inspectorPanel")?.scrollIntoView(); }}>
          参数
        </button>
        <button type="button" onClick={() => setMode("decision")}>
          结果
        </button>
      </nav>
      <div className={`toast${toast ? " show" : ""}`} role="status">
        {toast}
      </div>
    </div>
  );
}
