import { useEffect, useMemo, useRef, useState } from "react";
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
import { snapCenter, type Guide, type Tone } from "../canvas/geom";
import { LayoutCanvas, type CanvasHandle } from "../canvas/LayoutCanvas";
import { copy } from "../copy";
import { InspectorPanel } from "../inspector/InspectorPanel";
import { LibraryPanel } from "../library/LibraryPanel";
import { catalogItem, isPlaceable, type CatalogGroup } from "../library/catalog";
import { readAccepted, rememberAccepted } from "../persist/lastAccepted.js";
import { PreparePanel } from "../prepare/PreparePanel";
import {
  SPEC_PACKS,
  applyNormFix,
  auditNorms,
  normKeyOf,
  normNote,
  normSummary,
  type NormFinding,
  type NormPhase,
  type SpecPackId,
} from "../prepare/norms";
import { acceptRun, staleMessage } from "../run-cards/format.js";
import { actorsAt, segmentBounds, type Segment } from "../run-cards/playback";
import { RunCards } from "../run-cards/RunCards";
import {
  MIXED_TEMPLATE_ID,
  aisleOf,
  asBox,
  buildDemand,
  buildFacility,
  buildLayout,
  buildOperating,
  draftFor,
  elementFromDrop,
  emptyScenario,
  horizonSec,
  missingScenario,
  parseNum,
  columnsFor,
  rebindAccess,
  scenarioKey,
  specOf,
  testScenario,
  verdictFor,
  type Draft,
  type PlaceableType,
  type PoseEl,
  type ScenarioFields,
} from "./draft";

type Check = { status?: string; message?: string; objectIds?: string[]; ruleId?: string };
type Bound = { layoutRevision: string; outbound: string; scenarioKey: string };
type Ghost = {
  typeId: string;
  clientX: number;
  clientY: number;
  x: number;
  y: number;
  lengthM: number;
  widthM: number;
  heightM: number;
  yawDeg: number;
  tone: Tone;
  label: string;
  detail?: string;
};

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
  const elements = ((document.elements as Array<Record<string, unknown>>) ?? []).flatMap((el) => {
    const type = String(el.typeElementId);
    if (!isPlaceable(type)) return [];
    const spec = catalogItem(type);
    if (!spec) return [];
    const pose = (el.pose as { x: number; y: number; yawDeg?: number }) ?? { x: 0, y: 0 };
    const params = (el.params as Record<string, unknown>) ?? {};
    const access = params.accessPoint as { x?: number; y?: number } | undefined;
    const lengthM = numberOr(params.length_m, spec.lengthM);
    const widthM = numberOr(params.width_m, spec.widthM);
    const heightM = numberOr(params.height_m, spec.heightM);
    return [
      {
        instanceId: String(el.instanceId),
        typeElementId: type as PlaceableType,
        x: pose.x,
        y: pose.y,
        yawDeg: pose.yawDeg ?? numberOr(params.orientation_deg, spec.orientationDeg),
        lengthM,
        widthM,
        heightM,
        accessNodeId: typeof params.accessNodeId === "string" ? params.accessNodeId : null,
        accessX: typeof access?.x === "number" ? access.x : null,
        accessY: typeof access?.y === "number" ? access.y : null,
        bays: typeof params.bays === "number" ? params.bays : spec.defaultBays,
        levels: typeof params.levels === "number" ? params.levels : spec.defaultLevels,
        palletsPerBay: typeof params.palletsPerBay === "number" ? params.palletsPerBay : spec.palletsPerBay,
        minClearWidthM: typeof params.minClearWidthM === "number" ? params.minClearWidthM : spec.minClearWidthM,
      },
    ];
  });
  return {
    templateId: null,
    widthM: String(width),
    heightM: String(height),
    aisleWidthM: aisle?.widthM === undefined ? "" : String(aisle.widthM),
    aisleFromX: line[0] ? String(line[0].x) : "",
    aisleToX: line.length ? String(line[line.length - 1].x) : "",
    aisleY: line[0] ? String(line[0].y) : "",
    elements,
  };
}

function numberOr(value: unknown, fallback: number): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function Workbench() {
  const [mode, setMode] = useState<"edit" | "decision">("edit");
  const [draft, setDraft] = useState<Draft>(() => draftFor("mixed"));
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
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | CatalogGroup>("all");
  const [prepare, setPrepare] = useState<{ ready: boolean; checks: Check[]; snapshot: Record<string, unknown> | null } | null>(null);
  const [specOn, setSpecOn] = useState<Record<SpecPackId, boolean>>({ "fire-egress": false, "structure-bay": false });
  const [normAudit, setNormAudit] = useState<{ key: string; findings: NormFinding[] } | null>(null);
  const [run, setRun] = useState<Record<string, unknown> | null>(null);
  const [bound, setBound] = useState<Bound | null>(null);
  const [rejected, setRejected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [showGrid, setShowGrid] = useState(true);
  const [showLinks, setShowLinks] = useState(true);
  const [relief, setRelief] = useState(true);
  const [testValues, setTestValues] = useState(false);
  const [simT, setSimT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [ghost, setGhost] = useState<Ghost | null>(null);
  const [guides, setGuides] = useState<Guide[]>([]);
  const [liveTone, setLiveTone] = useState<{ id: string; tone: Tone } | null>(null);
  const dragOrigin = useRef<Draft | null>(null);
  const readyHold = useRef<{ key: string; value: { ready: boolean; checks: Check[]; snapshot: Record<string, unknown> | null } } | null>(null);
  const dragRef = useRef<{ id: PlaceableType; x: number; y: number; moved: boolean } | null>(null);
  const canvasRef = useRef<CanvasHandle>(null);

  const dirty = JSON.stringify(draft) !== savedKey;
  const selectedEl = draft.elements.find((el) => el.instanceId === selected) ?? null;
  const segments = useMemo(
    () => ((run?.trajectory as { segments?: Segment[] } | undefined)?.segments) ?? [],
    [run],
  );
  const horizon = Number((run?.trajectory as { horizonSec?: number } | undefined)?.horizonSec ?? 0);
  const bounds = useMemo(() => segmentBounds(segments, horizon), [segments, horizon]);
  const actors = useMemo(() => (mode === "decision" ? actorsAt(segments, simT) : []), [mode, segments, simT]);
  const selectedPacks = SPEC_PACKS.filter((pack) => specOn[pack.id]).map((pack) => pack.id);
  const normKey = normKeyOf(draft, selectedPacks);
  const normFresh = normAudit?.key === normKey;
  const findings = normFresh ? normAudit.findings : [];
  const normPhase: NormPhase = selectedPacks.length === 0 ? "off" : !normFresh ? "stale" : findings.length ? "fail" : "pass";

  function note(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  }

  function publishDraft(next: Draft, recordHistory: boolean) {
    if (recordHistory) {
      setPast((items) => [...items, structuredClone(draft)].slice(-30));
      setFuture([]);
    }
    setDraft(next);
    const key = JSON.stringify(next);
    if (readyHold.current?.key === key) setPrepare(readyHold.current.value);
    else setPrepare(null);
  }

  function previewDrop(type: PlaceableType, clientX: number, clientY: number) {
    const meters = canvasRef.current?.metersFromClient(clientX, clientY);
    if (!meters) return null;
    const spec = specOf(type);
    const lengthM = spec.bayLengthM && spec.defaultBays ? spec.bayLengthM * spec.defaultBays : spec.lengthM;
    const heightM = spec.levelHeightM && spec.defaultLevels ? spec.levelHeightM * spec.defaultLevels : spec.heightM;
    const facilityW = parseNum(draft.widthM) ?? 0;
    const facilityH = parseNum(draft.heightM) ?? 0;
    const snapped = snapCenter(
      meters.x,
      meters.y,
      aisleOf(draft),
      draft.elements.map(asBox),
      lengthM,
      spec.widthM,
      spec.orientationDeg,
      facilityW,
      facilityH,
    );
    const probe = elementFromDrop(draft.elements, type, snapped.x, snapped.y, null);
    const verdict = verdictFor(draft, probe, probe.instanceId);
    return { spec, snapped, verdict, lengthM, heightM, probe };
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
      setPrepare(null);
    })();
    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    if (!run) return;
    setSimT(bounds.t0);
    setPlaying(true);
  }, [run, bounds.t0]);

  useEffect(() => {
    if (!playing || mode !== "decision") return;
    let handle = 0;
    let last = performance.now();
    const span = Math.max(1, bounds.t1 - bounds.t0);
    const rate = Math.min(40, Math.max(8, span / 18));
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setSimT((value) => {
        const start = value < bounds.t0 || value > bounds.t1 ? bounds.t0 : value;
        const next = start + dt * rate;
        return next > bounds.t1 ? bounds.t0 : next;
      });
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [playing, mode, bounds.t0, bounds.t1]);

  function choose(kind: "blank" | "rectangle" | "mixed") {
    setDraft(draftFor(kind));
    setPast([]);
    setFuture([]);
    setSavedKey(null);
    readyHold.current = null;
    setPrepare(null);
    setSelected(null);
    setGhost(null);
    setGuides([]);
  }

  function undo() {
    setPast((items) => {
      if (!items.length) return items;
      const previous = items[items.length - 1];
      setFuture((queue) => [draft, ...queue]);
      setDraft(previous);
      const key = JSON.stringify(previous);
      if (readyHold.current?.key === key) setPrepare(readyHold.current.value);
      else setPrepare(null);
      return items.slice(0, -1);
    });
  }

  function redo() {
    setFuture((items) => {
      if (!items.length) return items;
      const next = items[0];
      setPast((queue) => [...queue, draft]);
      setDraft(next);
      const key = JSON.stringify(next);
      if (readyHold.current?.key === key) setPrepare(readyHold.current.value);
      else setPrepare(null);
      return items.slice(1);
    });
  }

  function applyDraft(patch: Partial<Draft>) {
    const rebound = rebindAccess({ ...draft, ...patch });
    if (rebound.lost.length) {
      note(`${copy.noAccess} ${rebound.lost.join("、")}`);
      return;
    }
    for (const el of rebound.draft.elements) {
      const verdict = verdictFor(rebound.draft, el, el.instanceId);
      if (verdict.tone === "red") {
        note(verdict.reason);
        return;
      }
    }
    publishDraft(rebound.draft, true);
  }

  function applyElement(patch: Partial<PoseEl>) {
    if (!selectedEl) return;
    const next = { ...selectedEl, ...patch };
    if (!(next.lengthM > 0) || !(next.widthM > 0) || !(next.heightM > 0)) {
      note("长度、宽度和高度必须大于 0。");
      return;
    }
    const verdict = verdictFor(draft, next, next.instanceId);
    if (verdict.tone === "red") {
      note(verdict.reason);
      return;
    }
    const stored: PoseEl = {
      ...next,
      accessNodeId: verdict.access?.id ?? null,
      accessX: verdict.access?.x ?? null,
      accessY: verdict.access?.y ?? null,
    };
    publishDraft(
      { ...draft, elements: draft.elements.map((el) => (el.instanceId === stored.instanceId ? stored : el)) },
      true,
    );
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
      readyHold.current = null;
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
      const nextPrepare = { ready: Boolean(result.simulationReady), checks, snapshot: result.snapshot ?? null };
      setPrepare(nextPrepare);
      readyHold.current = nextPrepare.ready ? { key: JSON.stringify(draft), value: nextPrepare } : null;
      note(result.simulationReady ? "准备通过，可以推演" : copy.validationFail);
    } catch (error) {
      note(`${copy.validationFail} ${error instanceof Error ? error.message : ""}`);
    } finally {
      setBusy(false);
    }
  }

  function onAudit() {
    if (!selectedPacks.length) {
      note("还没勾选规范包。当前只做几何硬约束，不能据此说消防合规。");
      return;
    }
    const next = auditNorms(draft, selectedPacks);
    setNormAudit({ key: normKey, findings: next });
    note(next.length ? `校核有 ${next.length} 条硬冲突，不能推演。` : "规范校核没有硬冲突。");
  }

  function onFix(finding: NormFinding) {
    const next = applyNormFix(draft, finding);
    const rebound = rebindAccess(next);
    for (const el of rebound.draft.elements) {
      const verdict = verdictFor(rebound.draft, el, el.instanceId);
      if (verdict.tone === "red") {
        note(verdict.reason);
        return;
      }
    }
    publishDraft(rebound.draft, true);
    const nextFindings = auditNorms(rebound.draft, selectedPacks);
    setNormAudit({ key: normKeyOf(rebound.draft, selectedPacks), findings: nextFindings });
    note(
      nextFindings.length
        ? "这处已经挪开，还有别的硬冲突。"
        : "已按建议改开，规范硬冲突没有了。布局若变了，保存并准备后才能推演。",
    );
  }

  async function onRun() {
    if (normPhase === "stale") {
      note("已选规范包还没校核，不能推演。");
      return;
    }
    if (normPhase === "fail") {
      note("规范有硬冲突，不能推演。取消勾选，或按建议修好再校核。");
      return;
    }
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

  function warnIfSoft(reason: string, tone: Tone) {
    if (tone === "yellow" && (reason.includes("消防") || reason.includes("结构柱"))) note(reason);
  }

  const layoutChanged = Boolean(run && bound && layoutRev && bound.layoutRevision !== layoutRev);
  const demandChanged = Boolean(run && bound && bound.outbound !== scenario.outbound);
  const scenarioChanged = Boolean(run && bound && bound.scenarioKey !== scenarioKey(scenario));
  const stale = run ? staleMessage({ layoutChanged, demandChanged, scenarioChanged }) : null;
  const prepareIds = (prepare?.checks ?? [])
    .filter((check) => check.status === "fail")
    .flatMap((check) => check.objectIds ?? [])
    .filter((id) => draft.elements.some((el) => el.instanceId === id));
  const conflictIds = [...new Set([...prepareIds, ...findings.flatMap((finding) => finding.objectIds)].filter((id) => draft.elements.some((el) => el.instanceId === id)))];
  const alertColumnIds = [...new Set(findings.flatMap((finding) => finding.columnIds))];
  const aisleAlert = findings.some((finding) => finding.aisle);
  const fireLaneAlert = findings.some((finding) => finding.fireLane);
  const hardCount = new Set([...prepareIds, ...findings.flatMap((finding) => finding.objectIds)]).size;
  const statusText =
    normPhase === "fail" || conflictIds.length
      ? "硬冲突"
      : normPhase === "stale"
        ? "规范未校核"
        : dirty || !layoutRev
          ? "未保存"
          : prepare?.ready
            ? "可推演"
            : prepare
              ? "准备未通过"
              : "未准备";
  const statusClass =
    normPhase === "fail" || conflictIds.length || (prepare && !prepare.ready) ? "status-pill error" : statusText === "可推演" ? "status-pill" : "status-pill warn";
  const widthLabel = draft.widthM && draft.heightM ? `${draft.widthM} × ${draft.heightM} m` : copy.missing;
  const badge = stale
    ? stale
    : draft.templateId && !layoutRev
      ? draft.templateId
      : layoutRev
        ? `修订 ${layoutRev}`
        : "尚未保存";

  const canvas = (
    <LayoutCanvas
      ref={canvasRef}
      draft={draft}
      selected={selected}
      conflictIds={conflictIds}
      liveTone={liveTone}
      guides={guides}
      showGrid={showGrid}
      showLinks={showLinks}
      actors={actors}
      segments={segments}
      simT={simT}
      relief={relief}
      badge={badge}
      interactive={mode === "edit"}
      ghost={ghost}
      columns={columnsFor(draft)}
      alertColumnIds={alertColumnIds}
      aisleAlert={aisleAlert}
      fireLaneAlert={fireLaneAlert}
      onSelect={setSelected}
      onMove={(id, x, y, phase) => {
        const current = (dragOrigin.current ?? draft).elements.find((el) => el.instanceId === id) ?? draft.elements.find((el) => el.instanceId === id);
        if (!current) return;
        if (phase === "start") {
          dragOrigin.current = structuredClone(draft);
          return;
        }
        const base = dragOrigin.current ?? draft;
        const facilityW = parseNum(base.widthM) ?? 0;
        const facilityH = parseNum(base.heightM) ?? 0;
        const snapped = snapCenter(
          x,
          y,
          aisleOf(base),
          base.elements.filter((el) => el.instanceId !== id).map(asBox),
          current.lengthM,
          current.widthM,
          current.yawDeg,
          facilityW,
          facilityH,
        );
        const probe = { ...current, x: snapped.x, y: snapped.y };
        const verdict = verdictFor(base, probe, id);
        const stored: PoseEl = {
          ...probe,
          accessNodeId: verdict.access?.id ?? null,
          accessX: verdict.access?.x ?? null,
          accessY: verdict.access?.y ?? null,
        };
        if (phase === "move") {
          setGuides(snapped.guides);
          setLiveTone({ id, tone: verdict.tone });
          setDraft((now) => ({ ...now, elements: now.elements.map((el) => (el.instanceId === id ? stored : el)) }));
          return;
        }
        setGuides([]);
        setLiveTone(null);
        if (verdict.tone === "red") {
          if (dragOrigin.current) setDraft(dragOrigin.current);
          note(verdict.reason);
          dragOrigin.current = null;
          return;
        }
        warnIfSoft(verdict.reason, verdict.tone);
        const movedDraft = { ...draft, elements: draft.elements.map((el) => (el.instanceId === id ? stored : el)) };
        setDraft(movedDraft);
        if (dragOrigin.current) {
          const origin = dragOrigin.current;
          const moved = origin.elements.some((el) => el.instanceId === id && (el.x !== stored.x || el.y !== stored.y));
          if (moved) {
            setPast((items) => [...items, origin].slice(-30));
            setFuture([]);
            const key = JSON.stringify(movedDraft);
            if (readyHold.current?.key === key) setPrepare(readyHold.current.value);
            else setPrepare(null);
          }
        }
        dragOrigin.current = null;
      }}
    />
  );

  return (
    <div className={`app${dragging ? " dragging" : ""}`}>
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
          <span className="topmeta">{draft.templateId ?? "人工摆放"}</span>
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
            dragging={dragging}
            query={query}
            filter={filter}
            onQuery={setQuery}
            onFilter={setFilter}
            onLocked={() => note(copy.unsupportedType)}
            onDragStart={(id, clientX, clientY) => {
              dragRef.current = { id: id as PlaceableType, x: clientX, y: clientY, moved: false };
              setDragging(id);
            }}
            onDragMove={(id, clientX, clientY) => {
              const drag = dragRef.current;
              if (!drag || drag.id !== id) return;
              if (Math.hypot(clientX - drag.x, clientY - drag.y) > 6) drag.moved = true;
              if (!drag.moved) return;
              const preview = previewDrop(drag.id, clientX, clientY);
              if (!preview) {
                setGhost(null);
                setGuides([]);
                return;
              }
              setGuides(preview.snapped.guides);
              setGhost({
                typeId: drag.id,
                clientX,
                clientY,
                x: preview.snapped.x,
                y: preview.snapped.y,
                lengthM: preview.lengthM,
                widthM: preview.spec.widthM,
                heightM: preview.heightM,
                yawDeg: preview.spec.orientationDeg,
                tone: preview.verdict.tone,
                label: preview.spec.name,
                detail: preview.verdict.tone === "green" ? "可放" : preview.verdict.reason,
              });
            }}
            onDragEnd={(id, clientX, clientY) => {
              const drag = dragRef.current;
              dragRef.current = null;
              setDragging(null);
              setGhost(null);
              setGuides([]);
              if (!drag || drag.id !== id || !drag.moved) return;
              if (mode !== "edit") {
                note("请先回到布局编辑再摆放。");
                return;
              }
              const preview = previewDrop(drag.id, clientX, clientY);
              if (!preview) {
                note("请把设备拖到场地画布上。");
                return;
              }
              if (preview.verdict.tone === "red") {
                note(preview.verdict.reason);
                return;
              }
              warnIfSoft(preview.verdict.reason, preview.verdict.tone);
              const element = elementFromDrop(draft.elements, drag.id, preview.snapped.x, preview.snapped.y, preview.verdict.access);
              publishDraft({ ...draft, elements: [...draft.elements, element] }, true);
              setSelected(element.instanceId);
            }}
          />
          <main className="main" id="editorMain">
            <div className="canvas-head">
              <div>
                <div className="canvas-title">综合仓布局</div>
                <div className="canvas-caption">
                  {draft.templateId ?? "人工摆放"} / {widthLabel} / {copy.view25}
                </div>
              </div>
              <div className="canvas-tools">
                <div className="view-switch">
                  <button type="button" className={relief ? "" : "active"} onClick={() => setRelief(false)}>
                    顶视
                  </button>
                  <button type="button" className={relief ? "active" : ""} onClick={() => setRelief(true)}>
                    2.5D
                  </button>
                </div>
                <button className="icon-btn" type="button" onClick={() => setShowGrid((value) => !value)} aria-label="切换网格">
                  格
                </button>
                <button className="icon-btn" type="button" onClick={() => setShowLinks((value) => !value)} aria-label="切换接入线">
                  线
                </button>
                <button className="ghost-btn" type="button" onClick={() => choose("mixed")}>
                  {MIXED_TEMPLATE_ID}
                </button>
                <button className="ghost-btn" type="button" onClick={() => choose("blank")}>
                  空白场地
                </button>
                <button className="ghost-btn" type="button" onClick={() => choose("rectangle")}>
                  矩形模板
                </button>
              </div>
            </div>
            {canvas}
            <div className="bottom-strip">
              <span className={statusClass}>{statusText}</span>
              <span className="stat">
                设备 <strong>{draft.elements.length}</strong>
              </span>
              <span className="stat">
                货架 <strong>{draft.elements.filter((el) => el.typeElementId === "ST-PAL-01").length}</strong>
              </span>
              <span className="stat">
                硬冲突 <strong>{hardCount}</strong>
              </span>
              <span className="stat">
                布局修订 <strong>{layoutRev ?? copy.notIssued}</strong>
              </span>
            </div>
          </main>
          <aside className="inspector" id="inspectorPanel">
            <InspectorPanel
              draft={draft}
              onDraft={applyDraft}
              selected={selectedEl}
              onElement={applyElement}
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
              normPhase={normPhase}
              normSummary={normSummary(normPhase, selectedPacks, findings.length)}
              normNote={normNote(normPhase, selectedPacks)}
              specOn={specOn}
              findings={findings}
              onToggleSpec={(id, checked) => setSpecOn((current) => ({ ...current, [id]: checked }))}
              onAudit={onAudit}
              onFix={onFix}
            />
            <PreparePanel
              busy={busy}
              canDelete={Boolean(selectedEl)}
              runLabel={run ? "再次推演" : "开始推演"}
              onPrepare={() => void onPrepare()}
              onDelete={() => {
                if (!selected) return;
                publishDraft({ ...draft, elements: draft.elements.filter((el) => el.instanceId !== selected) }, true);
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
          simT={simT}
          t0={bounds.t0}
          t1={bounds.t1}
          playing={playing}
          onSimT={(value) => {
            setPlaying(false);
            setSimT(value);
          }}
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
