import { useEffect, useMemo, useRef, useState } from "react";
import { CONTRACT_VERSION, EQUIP_SCHEMA_VERSION, SNAPSHOT_SCHEMA_VERSION } from "@simapp/contracts";
import { apiJson } from "./api";
import {
  buildFacility,
  buildLayout,
  buildOperating,
  buildPlanningDemand,
  buildSimDemand,
  demoCostBasis,
  demoPriceBook,
  demoScoreProfile,
  elementsFromDocument,
  templateElements,
  type PlacedElement,
} from "./documents";
import { CATEGORIES, LIBRARY, defaultParams, libraryItem, type LibraryItem } from "./library";

type View = "layout" | "results" | "compare";

type Check = { ruleId: string; status: string; message: string };

type PrepareState = {
  simulationReady: boolean;
  prepareStatus: string;
  validationStatus: string;
  layoutRevision: string;
  checks: Check[];
};

type Cards = {
  throughput?: { value?: number | null; unit?: string; outboundPalletEq?: number };
  wait?: {
    meanSec?: number | null;
    p95Sec?: number | null;
    sampleCount?: number;
    unit?: string;
    p95Meta?: { sampleInsufficient?: boolean };
  };
  utilization?: { value?: number | null; unit?: string; note?: string };
  bottleneck?: { top1?: { entityId?: string | null; note?: string; waitSec?: number } };
};

type DocRef = { id: string; revision: string };

type SimState = {
  runId: string;
  layoutRevision: string;
  cards: Cards;
  completionRate: number | null;
  completedTasks: number | null;
  incompleteTasks: number | null;
  warnings: string[];
  demandRef: DocRef;
  operatingRef: DocRef;
  forkliftCount: number;
};

type Candidate = {
  id: string;
  evaluationLevel?: string;
  claimsOperationalEfficiency?: boolean;
  metrics?: Record<string, { value?: number | null; unit?: string; status?: string }>;
};

type FailureCard = {
  capability: string;
  status: string;
  code: string;
  message: string;
  correction: string;
};

type CompareRow = {
  label?: string;
  effectiveCapacity?: number | null;
  completedCycleMeanSec?: number | null;
  outboundThroughput?: number | null;
  waitMeanSec?: number | null;
  capex?: number | null;
  costStatus?: string | null;
  layoutRevision?: string | null;
  runId?: string | null;
  resourceFingerprint?: Record<string, number | string>;
};

type CompareState = {
  id: string;
  mode: string;
  kpiFromUiDemo: boolean;
  radarEnabled: boolean;
  radarNote: string;
  series: Array<{ entryId?: string; label?: string; points?: Array<{ axisId: string; score: number | null }> }>;
  rows: CompareRow[];
  issues: string[];
};

type WorkspacePayload = {
  project: { id: string; name?: string };
  facility?: { revision?: string; boundary?: { outer?: Array<{ x: number; y: number }> } } | null;
  layout?: {
    id: string;
    revision: string;
    aisles?: Array<{ widthM?: number; centerline?: Array<{ y?: number }> }>;
  } | null;
  variant?: { id: string; revision: string } | null;
  prepare?: PrepareState | null;
  operating?: { resourcePools?: Array<{ resourceType?: string; count?: number }> } | null;
  demand?: { flows?: Array<{ intent?: string; quantity?: number }> } | null;
  run?: {
    runId: string;
    layoutRevision: string;
    kpi?: {
      cards?: Cards;
      secondary?: { completionRate?: number | null; completedTasks?: number; incompleteTasks?: number };
    };
    runManifest?: { demandRef?: DocRef; operatingRef?: DocRef; warnings?: Array<{ code?: string } | string> };
  } | null;
  comparison?: {
    id: string;
    mode: string;
    kpiFromUiDemo?: boolean;
    radar?: { radarEnabled?: boolean; note?: string; series?: CompareState["series"] };
    table?: { rows?: CompareRow[] };
    comparability?: { issues?: Array<{ message?: string; code?: string }> };
  } | null;
  persistence?: { engine?: string; durable?: boolean };
};

type SavedRefs = {
  projectId: string;
  facilityRevision: string;
  layoutId: string;
  layoutRevision: string;
  variantId: string;
  variantRevision: string;
};

const ALT_LAYOUT_ID = "layout-workbench-alt";

function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function cloneElements(elements: PlacedElement[]): PlacedElement[] {
  return elements.map((el) => ({ ...el, params: { ...el.params } }));
}

function warningCodes(warnings: Array<{ code?: string } | string> | undefined): string[] {
  return (warnings ?? [])
    .map((item) => (typeof item === "string" ? item : item.code || ""))
    .filter((code) => code.length > 0);
}

function compareFromApi(comparison: NonNullable<WorkspacePayload["comparison"]>): CompareState {
  return {
    id: comparison.id,
    mode: comparison.mode,
    kpiFromUiDemo: comparison.kpiFromUiDemo === true,
    radarEnabled: comparison.radar?.radarEnabled === true,
    radarNote: comparison.radar?.note || "缺失值不绘为 0",
    series: comparison.radar?.series ?? [],
    rows: comparison.table?.rows ?? [],
    issues: (comparison.comparability?.issues ?? []).map((item) =>
      [item.code, item.message].filter(Boolean).join("："),
    ),
  };
}

function fingerprintText(fp: CompareRow["resourceFingerprint"]): string {
  if (!fp) return "—";
  const parts = Object.entries(fp).map(([key, value]) => `${key}=${value}`);
  return parts.length ? parts.join("，") : "—";
}

export function App() {
  const [view, setView] = useState<View>("layout");
  const [query, setQuery] = useState("");
  const [armed, setArmed] = useState<LibraryItem | null>(null);
  const [widthM, setWidthM] = useState(40);
  const [depthM, setDepthM] = useState(24);
  const [aisleWidthM, setAisleWidthM] = useState(3.5);
  const [aisleYM, setAisleYM] = useState(12);
  const [elements, setElements] = useState<PlacedElement[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState("还没有布局。可以从元素库摆放、使用模板，或帮我生成。");
  const [prepare, setPrepare] = useState<PrepareState | null>(null);
  const [sim, setSim] = useState<SimState | null>(null);
  const [saved, setSaved] = useState<SavedRefs | null>(null);
  const [outboundQty, setOutboundQty] = useState(4);
  const [forkliftCount, setForkliftCount] = useState(1);
  const [planOpen, setPlanOpen] = useState(false);
  const [planOutcome, setPlanOutcome] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [disabledGoals, setDisabledGoals] = useState<string[]>([]);
  const [compare, setCompare] = useState<CompareState | null>(null);
  const [storeNote, setStoreNote] = useState("本地库");
  const [recognition, setRecognition] = useState<FailureCard | null>(null);
  const [recCapability, setRecCapability] = useState("dxf_vector_extract");
  const [recFile, setRecFile] = useState("hall.dxf");
  const seq = useRef(1);
  const history = useRef<PlacedElement[][]>([]);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      try {
        const listed = await apiJson<{ items: Array<{ id: string; name: string }> }>("/api/v1/projects");
        const named = listed.items.filter((item) => item.name === "工作台方案");
        const pick = (named.length ? named : listed.items)[0];
        if (!pick || cancelled) {
          if (!cancelled) setStoreNote(listed.items.length ? "本地库" : "本地库 · 还没有已保存方案");
          return;
        }
        const ws = await apiJson<WorkspacePayload>(`/api/v1/projects/${pick.id}/workspace`);
        if (cancelled) return;
        const placed = ws.layout ? elementsFromDocument(ws.layout) : [];
        if (placed.length) {
          setElements(placed);
          const maxSeq = placed.reduce((max, el) => {
            const match = /-(\d+)$/.exec(el.instanceId);
            return match ? Math.max(max, Number(match[1]) + 1) : max;
          }, 1);
          seq.current = Math.max(seq.current, maxSeq);
        }
        const outer = ws.facility?.boundary?.outer ?? [];
        if (outer.length) {
          setWidthM(Math.max(...outer.map((point) => point.x)));
          setDepthM(Math.max(...outer.map((point) => point.y)));
        }
        const aisle = ws.layout?.aisles?.[0];
        if (aisle?.widthM) setAisleWidthM(aisle.widthM);
        const aisleY = aisle?.centerline?.[0]?.y;
        if (typeof aisleY === "number") setAisleYM(aisleY);
        if (ws.layout) {
          setSaved({
            projectId: ws.project.id,
            facilityRevision: ws.facility?.revision || "",
            layoutId: ws.layout.id,
            layoutRevision: ws.layout.revision,
            variantId: ws.variant?.id || "",
            variantRevision: ws.variant?.revision || "",
          });
        }
        if (ws.prepare) setPrepare(ws.prepare);
        const pool = ws.operating?.resourcePools?.find((item) => item.resourceType === "forklift");
        if (pool?.count) setForkliftCount(pool.count);
        const outbound = ws.demand?.flows?.find((flow) => flow.intent === "outbound")?.quantity;
        if (typeof outbound === "number") setOutboundQty(outbound);
        const demandRef = ws.run?.runManifest?.demandRef;
        const operatingRef = ws.run?.runManifest?.operatingRef;
        if (ws.run && demandRef?.id && operatingRef?.id) {
          setSim({
            runId: ws.run.runId,
            layoutRevision: ws.run.layoutRevision,
            cards: ws.run.kpi?.cards ?? {},
            completionRate: ws.run.kpi?.secondary?.completionRate ?? null,
            completedTasks: ws.run.kpi?.secondary?.completedTasks ?? null,
            incompleteTasks: ws.run.kpi?.secondary?.incompleteTasks ?? null,
            warnings: warningCodes(ws.run.runManifest?.warnings),
            demandRef,
            operatingRef,
            forkliftCount: pool?.count || 1,
          });
        }
        if (ws.comparison) setCompare(compareFromApi(ws.comparison));
        setDirty(false);
        const durable = ws.persistence?.durable !== false;
        setStoreNote(durable ? "本地库 · 已恢复" : "内存模式 · 已恢复");
        setStatusNote(
          ws.layout
            ? `已从本地库恢复「${ws.project.name || "方案"}」。布局、准备和跑次都还在。`
            : "本地库里有项目，但还没有布局。",
        );
      } catch {
        if (!cancelled) setStoreNote("未连上 API");
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = elements.find((el) => el.instanceId === selectedId) ?? null;
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return LIBRARY;
    return LIBRARY.filter(
      (item) =>
        item.name.toLowerCase().includes(q) || item.typeElementId.toLowerCase().includes(q),
    );
  }, [query]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
      if (event.key === "Escape") setArmed(null);
      if (typing) return;
      if ((event.key === "Delete" || event.key === "Backspace") && selectedId) {
        event.preventDefault();
        removeSelected(selectedId);
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        undo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function remember() {
    history.current = [...history.current.slice(-30), cloneElements(elements)];
  }

  function undo() {
    const prev = history.current.pop();
    if (!prev) return;
    setElements(prev);
    setDirty(true);
    setStatusNote("已撤销本地摆放。保存后的修订不会被这条撤销改写。");
  }

  function touch(next: PlacedElement[]) {
    remember();
    setElements(next);
    setDirty(true);
    setStatusNote("布局已改，尚未保存。");
  }

  function place(item: LibraryItem, x: number, y: number) {
    const params = defaultParams(item);
    const w = params.footprintW;
    const d = params.footprintD;
    const cx = Math.min(Math.max(x, w / 2), Math.max(w / 2, widthM - w / 2));
    const cy = Math.min(Math.max(y, d / 2), Math.max(d / 2, depthM - d / 2));
    const instanceId = `${item.typeElementId.toLowerCase()}-${seq.current++}`;
    touch([
      ...elements,
      {
        instanceId,
        typeElementId: item.typeElementId,
        x: Number(cx.toFixed(3)),
        y: Number(cy.toFixed(3)),
        yawDeg: 0,
        params,
        assetDisposition: "new",
      },
    ]);
    setSelectedId(instanceId);
    setArmed(null);
  }

  function updateSelected(patch: Partial<PlacedElement> = {}, params?: Record<string, number>) {
    if (!selected) return;
    remember();
    setElements(
      elements.map((el) =>
        el.instanceId === selected.instanceId
          ? { ...el, ...patch, params: params ?? el.params }
          : el,
      ),
    );
    setDirty(true);
  }

  function removeSelected(instanceId: string) {
    touch(elements.filter((el) => el.instanceId !== instanceId));
    setSelectedId(null);
  }

  function applyTemplate() {
    remember();
    setWidthM(40);
    setDepthM(24);
    setAisleWidthM(3.5);
    setAisleYM(12);
    setElements(templateElements());
    setSelectedId("rack-001");
    setDirty(true);
    setArmed(null);
    setStatusNote("已放入矩形仓模板。这是可编辑布局，保存并准备后才能推演。");
  }

  async function persist(): Promise<SavedRefs> {
    const project = saved
      ? { id: saved.projectId }
      : await apiJson<{ id: string }>("/api/v1/projects", {
          method: "POST",
          body: JSON.stringify({ name: "工作台方案", unitSystem: "metric" }),
        });
    const facilityRevision = `f-ui-${Date.now().toString(36)}-${seq.current++}`;
    const facility = buildFacility(widthM, depthM, facilityRevision);
    const facilityRes = await apiJson<{ gate?: { usableForValidatedPlanning?: boolean } }>(
      `/api/v1/projects/${project.id}/facility-revisions`,
      { method: "POST", body: JSON.stringify({ facility }) },
    );
    const layoutId = saved?.layoutId ?? "layout-workbench";
    const layoutRevision = `ld-ui-${Date.now().toString(36)}-${seq.current++}`;
    const document = buildLayout({
      layoutId,
      revision: layoutRevision,
      facilityRevision,
      elements,
      widthM,
      depthM,
      aisleWidthM,
      aisleYM,
    });
    const savedLayout = await apiJson<{ layoutRef: { id: string; revision: string } }>(
      `/api/v1/layouts/${layoutId}/revisions`,
      {
        method: "POST",
        body: JSON.stringify({
          projectId: project.id,
          baseRevision: saved && saved.layoutId === layoutId && saved.layoutRevision ? saved.layoutRevision : null,
          document,
        }),
      },
    );
    const variant = await apiJson<{ id: string; revision: string }>(
      `/api/v1/projects/${project.id}/variants`,
      {
        method: "POST",
        body: JSON.stringify({
          name: "手动方案",
          source: "manual",
          layoutRef: savedLayout.layoutRef,
        }),
      },
    );
    const refs: SavedRefs = {
      projectId: project.id,
      facilityRevision,
      layoutId: savedLayout.layoutRef.id,
      layoutRevision: savedLayout.layoutRef.revision,
      variantId: variant.id,
      variantRevision: variant.revision,
    };
    setSaved(refs);
    setDirty(false);
    if (facilityRes.gate && facilityRes.gate.usableForValidatedPlanning === false) {
      setStatusNote("场地已保存，但规划门禁未通过。手动准备仍会继续。");
    }
    return refs;
  }

  async function prepareLayout(refs: SavedRefs, publish = true): Promise<PrepareState> {
    const body = await apiJson<{
      simulationReady: boolean;
      prepareStatus: string;
      validationStatus: string;
      layoutRevision: string;
      validationReport?: { checks?: Check[] };
    }>(`/api/v1/layouts/${refs.layoutId}/prepare-jobs`, {
      method: "POST",
      body: JSON.stringify({
        projectId: refs.projectId,
        layoutRef: { id: refs.layoutId, revision: refs.layoutRevision },
        facilityRef: { id: "facility-workbench", revision: refs.facilityRevision },
        ruleSetRefs: [{ id: "ruleset.m1.geometry", revision: "0.1" }],
        sync: true,
      }),
    });
    const next: PrepareState = {
      simulationReady: body.simulationReady,
      prepareStatus: body.prepareStatus,
      validationStatus: body.validationStatus,
      layoutRevision: body.layoutRevision,
      checks: body.validationReport?.checks ?? [],
    };
    if (publish) setPrepare(next);
    return next;
  }

  async function onPrepare() {
    setBusy(true);
    setError(null);
    try {
      const refs = await persist();
      const ready = await prepareLayout(refs);
      setStatusNote(
        ready.simulationReady
          ? `已保存并准备。layoutRevision=${ready.layoutRevision}，可以推演。`
          : "已保存，校验未通过。未启动推演。",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSimulate() {
    setBusy(true);
    setError(null);
    try {
      const refs = await persist();
      const ready = await prepareLayout(refs);
      if (!ready.simulationReady) {
        setStatusNote("校验未通过，后端拒绝推演。请先看右栏原因。");
        setView("layout");
        return;
      }
      const rack = elements.find((el) => el.typeElementId.startsWith("ST-"));
      if (!rack) {
        setStatusNote("开始推演前需要至少一台托盘货架，用来放置初始库存。");
        setView("layout");
        return;
      }
      const demandRev = `d-ui-${Date.now().toString(36)}-${seq.current++}`;
      const opRev = `o-ui-${Date.now().toString(36)}-${seq.current++}`;
      const demand = buildSimDemand(outboundQty, demandRev, rack.instanceId);
      const operating = buildOperating(forkliftCount, opRev);
      await apiJson("/api/v1/demands", {
        method: "POST",
        body: JSON.stringify({ projectId: refs.projectId, demand }),
      });
      await apiJson("/api/v1/operating-profiles", {
        method: "POST",
        body: JSON.stringify({ projectId: refs.projectId, operating }),
      });
      const result = await apiJson<{
        runId: string;
        layoutRevision: string;
        kpi?: { cards?: Cards; secondary?: { completionRate?: number | null; completedTasks?: number; incompleteTasks?: number } };
        warnings?: Array<{ code: string }>;
      }>("/api/v1/simulation-jobs", {
        method: "POST",
        body: JSON.stringify({
          projectId: refs.projectId,
          variantRef: { id: refs.variantId, revision: refs.variantRevision },
          scenarioPackage: {
            contractVersion: "0.3",
            scenarioId: "scenario-workbench",
            demandRef: { id: demand.id, revision: demand.revision },
            operatingRef: { id: operating.id, revision: operating.revision },
            runControl: {
              horizonSec: 3600,
              seedStreams: { demand: 42, dispatch: 42 },
              demandSampleRef: null,
              metricDefinitionVersion: "metrics-m3-v1",
            },
            expectedLayoutRevision: refs.layoutRevision,
          },
        }),
      });
      setSim({
        runId: result.runId,
        layoutRevision: result.layoutRevision,
        cards: result.kpi?.cards ?? {},
        completionRate: result.kpi?.secondary?.completionRate ?? null,
        completedTasks: result.kpi?.secondary?.completedTasks ?? null,
        incompleteTasks: result.kpi?.secondary?.incompleteTasks ?? null,
        warnings: (result.warnings ?? []).map((item) => item.code),
        demandRef: { id: demand.id, revision: demand.revision },
        operatingRef: { id: operating.id, revision: operating.revision },
        forkliftCount,
      });
      setStatusNote(`推演完成 runId=${result.runId}。四卡来自事件，不是界面公式。`);
      setView("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPlan() {
    setBusy(true);
    setError(null);
    setPlanOpen(true);
    try {
      const refs = await persist();
      await apiJson("/api/v1/demands", {
        method: "POST",
        body: JSON.stringify({ projectId: refs.projectId, demand: buildPlanningDemand() }),
      });
      const draft = await apiJson<{ disabledGoals?: Array<{ goal: string; reason: string }> }>(
        `/api/v1/projects/${refs.projectId}/planning-drafts`,
        {
          method: "POST",
          body: JSON.stringify({
            request: {
              contractVersion: "0.3",
              goals: ["capacity", "efficiency", "lifecycle_cost"],
              evaluationLevel: "quick",
            },
          }),
        },
      );
      setDisabledGoals(
        (draft.disabledGoals ?? []).map((item) => `${item.goal}：${item.reason}`),
      );
      const plan = await apiJson<{
        outcome?: string;
        terminationReason?: string;
        candidates?: Candidate[];
      }>("/api/v1/planning-jobs", {
        method: "POST",
        body: JSON.stringify({
          contractVersion: "0.3",
          projectId: refs.projectId,
          facilityRef: { id: "facility-workbench", revision: refs.facilityRevision },
          baseVariantRef: { id: refs.variantId, revision: refs.variantRevision },
          demandRef: { id: "demand-plan-ui", revision: "d-plan-1" },
          scope: { mode: "whole" },
          locks: [],
          goals: ["capacity"],
          constraints: { allowedTypeIds: ["ST-PAL-01", "IN-DOCK-01", "OUT-DOCK-01"] },
          evaluationLevel: "quick",
          budget: { maxConfigurations: 50, maxIterations: 1000, maxWallTimeSec: 30, maxMemoryMb: 512 },
          seed: 42,
          catalogRef: { id: "catalog-mvp", revision: "c-r1" },
          templateSetRef: { id: "template-rect", revision: "t-r1" },
          ruleSetRefs: [],
        }),
      });
      setPlanOutcome(
        [plan.outcome, plan.terminationReason].filter(Boolean).join(" · ") || "无结果",
      );
      setCandidates(plan.candidates ?? []);
      setStatusNote("规划结束。quick 只是几何/路径估算，不是运营效率。");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function adopt(candidateId: string) {
    if (!saved) return;
    setBusy(true);
    setError(null);
    try {
      const adopted = await apiJson<{
        variant: { id: string; revision: string };
        layoutRef: { id: string; revision: string };
        claimsOperationalEfficiency?: boolean;
        note?: string;
      }>(`/api/v1/candidates/${candidateId}/adoptions`, {
        method: "POST",
        body: JSON.stringify({
          projectId: saved.projectId,
          currentVariantRef: { id: saved.variantId, revision: saved.variantRevision },
          newName: "生成方案",
          expectedVariantRevision: saved.variantRevision,
        }),
      });
      const loaded = await apiJson<{ document: unknown }>(
        `/api/v1/layouts/${adopted.layoutRef.id}/revisions/${adopted.layoutRef.revision}?projectId=${saved.projectId}`,
      );
      remember();
      setElements(elementsFromDocument(loaded.document));
      setSaved({
        ...saved,
        layoutId: adopted.layoutRef.id,
        layoutRevision: adopted.layoutRef.revision,
        variantId: adopted.variant.id,
        variantRevision: adopted.variant.revision,
      });
      setDirty(false);
      setPrepare(null);
      setPlanOpen(false);
      setSelectedId(null);
      setStatusNote(
        adopted.claimsOperationalEfficiency
          ? "采用返回了不应出现的效率声明。"
          : "已采用为新方案分支，原底稿未覆盖。需重新准备后才能推演。",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRecognize() {
    setBusy(true);
    setError(null);
    try {
      const refs = saved ?? (await persist());
      const mediaType = recFile.toLowerCase().endsWith(".dxf")
        ? "application/dxf"
        : recFile.toLowerCase().endsWith(".png")
          ? "image/png"
          : "application/pdf";
      const drawing = await apiJson<{ id: string }>(`/api/v1/projects/${refs.projectId}/drawings`, {
        method: "POST",
        body: JSON.stringify({
          filename: recFile || "untitled",
          status: "uploaded",
          meta: recCapability === "polygon_height_partition" ? { scaleDeclared: true } : {},
        }),
      });
      const result = await apiJson<{
        status: string;
        failure?: { code: string; message: string };
        correction?: { message: string };
        producedGeometry: unknown;
        claimsValidatedGeometry: boolean;
        score?: number | null;
      }>("/api/v1/recognition-jobs", {
        method: "POST",
        body: JSON.stringify({
          projectId: refs.projectId,
          drawingId: drawing.id,
          capability: recCapability,
          source: {
            filename: recFile,
            mediaType,
            scaleDeclared: recCapability === "polygon_height_partition",
            ocrConfidence: recCapability === "ocr_assist" ? 0.99 : undefined,
            floors: 1,
            heightZones: 1,
          },
        }),
      });
      setRecognition({
        capability: recCapability,
        status: result.status,
        code: result.failure?.code ?? "UNKNOWN",
        message: result.failure?.message ?? "无说明",
        correction: result.correction?.message ?? "",
      });
      if (result.producedGeometry || result.claimsValidatedGeometry) {
        setError("识图接口返回了几何，这与 M5 失败路径不符。");
      } else {
        setStatusNote("识图未生成场地。底图仍在，请按校正说明手工处理。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onCostCompare() {
    if (!saved?.projectId || !saved.variantId || !sim) {
      setStatusNote("先完成一次推演，再估算成本并对比。");
      setView("results");
      return;
    }
    if (dirty) {
      setStatusNote("布局已改。先重新推演，再用这次跑次和叉车加一的方案对比。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const projectId = saved.projectId;
      const priceBook = demoPriceBook();
      const costBasis = demoCostBasis();
      const scoreProfile = demoScoreProfile();
      const postedBook = await apiJson<{ demoOnly?: boolean }>("/api/v1/price-books", {
        method: "POST",
        body: JSON.stringify({ projectId, priceBook }),
      });
      if (postedBook.demoOnly !== true) {
        throw new Error("价目未标 demoOnly，已停止，避免把演示价当成正式报价。");
      }
      await apiJson("/api/v1/cost-bases", {
        method: "POST",
        body: JSON.stringify({ projectId, costBasis }),
      });
      await apiJson("/api/v1/score-profiles", {
        method: "POST",
        body: JSON.stringify({ projectId, scoreProfile }),
      });

      const estimate = async (variant: DocRef, layout: DocRef, operating: DocRef) =>
        apiJson<{ costEstimateId: string; status: string; totals?: { capex?: number | null } }>(
          "/api/v1/cost-estimate-jobs",
          {
            method: "POST",
            body: JSON.stringify({
              projectId,
              variantRef: variant,
              layoutRef: layout,
              priceBookRef: { id: priceBook.id, revision: priceBook.revision },
              costBasisRef: { id: costBasis.id, revision: costBasis.revision },
              operatingRef: operating,
              sync: true,
            }),
          },
        );

      const currentLayout = { id: saved.layoutId, revision: saved.layoutRevision };
      const currentVariant = { id: saved.variantId, revision: saved.variantRevision };
      const currentCost = await estimate(currentVariant, currentLayout, sim.operatingRef);

      const altRevision = `ld-alt-${Date.now().toString(36)}-${seq.current++}`;
      const altDocument = buildLayout({
        layoutId: ALT_LAYOUT_ID,
        revision: altRevision,
        facilityRevision: saved.facilityRevision,
        elements,
        widthM,
        depthM,
        aisleWidthM,
        aisleYM,
      });
      const altSaved = await apiJson<{ layoutRef: DocRef }>(`/api/v1/layouts/${ALT_LAYOUT_ID}/revisions`, {
        method: "POST",
        body: JSON.stringify({ projectId, baseRevision: null, document: altDocument }),
      });
      const altVariant = await apiJson<DocRef>(`/api/v1/projects/${projectId}/variants`, {
        method: "POST",
        body: JSON.stringify({
          name: "叉车加一",
          source: "manual",
          layoutRef: altSaved.layoutRef,
        }),
      });
      const altReady = await prepareLayout(
        {
          projectId,
          facilityRevision: saved.facilityRevision,
          layoutId: altSaved.layoutRef.id,
          layoutRevision: altSaved.layoutRef.revision,
          variantId: altVariant.id,
          variantRevision: altVariant.revision,
        },
        false,
      );
      if (!altReady.simulationReady) {
        throw new Error("叉车加一的布局校验未通过，没有做对比。");
      }
      const altCount = sim.forkliftCount + 1;
      const altOperating = buildOperating(altCount, `o-alt-${Date.now().toString(36)}-${seq.current++}`);
      await apiJson("/api/v1/operating-profiles", {
        method: "POST",
        body: JSON.stringify({ projectId, operating: altOperating }),
      });
      const altRun = await apiJson<{ runId: string }>("/api/v1/simulation-jobs", {
        method: "POST",
        body: JSON.stringify({
          projectId,
          variantRef: altVariant,
          scenarioPackage: {
            contractVersion: "0.3",
            scenarioId: "scenario-workbench-alt",
            demandRef: sim.demandRef,
            operatingRef: { id: altOperating.id, revision: altOperating.revision },
            runControl: {
              horizonSec: 3600,
              seedStreams: { demand: 42, dispatch: 42 },
              demandSampleRef: null,
              metricDefinitionVersion: "metrics-m3-v1",
            },
            expectedLayoutRevision: altSaved.layoutRef.revision,
          },
        }),
      });
      const altCost = await estimate(altVariant, altSaved.layoutRef, {
        id: altOperating.id,
        revision: altOperating.revision,
      });

      const body = await apiJson<{ comparison: NonNullable<WorkspacePayload["comparison"]> }>(
        "/api/v1/comparisons",
        {
          method: "POST",
          body: JSON.stringify({
            projectId,
            mode: "whole_solution",
            commonBasis: {
              demandRef: sim.demandRef,
              engineVersion: "m3-des-0.1",
            },
            scoreProfileRef: { id: scoreProfile.id, revision: scoreProfile.revision },
            entries: [
              {
                entryId: "current",
                label: "当前方案",
                variantRef: currentVariant,
                layoutRef: currentLayout,
                runId: sim.runId,
                costEstimateId: currentCost.costEstimateId,
                operatingRef: sim.operatingRef,
              },
              {
                entryId: "forklift-plus",
                label: `叉车 ${altCount}`,
                variantRef: altVariant,
                layoutRef: altSaved.layoutRef,
                runId: altRun.runId,
                costEstimateId: altCost.costEstimateId,
                operatingRef: { id: altOperating.id, revision: altOperating.revision },
              },
            ],
          }),
        },
      );
      const next = compareFromApi(body.comparison);
      if (next.kpiFromUiDemo) {
        throw new Error("比较结果标记了界面公式，已丢弃。");
      }
      setCompare(next);
      setStatusNote("对比来自 /comparisons。周期缺失保持空，不拿等待均值代替。价目是 demo 输入。");
      setView("compare");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function onCanvasClick(event: React.MouseEvent<SVGSVGElement>) {
    if (!armed) return;
    const svg = event.currentTarget;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = svg.getScreenCTM();
    if (!matrix) return;
    const loc = point.matrixTransform(matrix.inverse());
    place(armed, loc.x, depthM - loc.y);
  }

  const failedChecks = (prepare?.checks ?? []).filter((check) => check.status !== "pass");
  const saveLabel = dirty
    ? "未保存"
    : prepare?.simulationReady
      ? "可推演"
      : prepare
        ? "校验未通过"
        : saved
          ? "已保存"
          : "未保存";

  return (
    <div className="workbench">
      <header className="topbar">
        <div>
          <strong>simapp</strong>
          <span className="muted"> 布局工作台</span>
        </div>
          <div className="muted">
            契约 {CONTRACT_VERSION} · Snapshot {SNAPSHOT_SCHEMA_VERSION} · equip {EQUIP_SCHEMA_VERSION} · {storeNote}
          </div>
        <div className={dirty ? "pill warn" : "pill"}>{saveLabel}</div>
      </header>
      <nav className="views">
        {(
          [
            ["layout", "布局工作台"],
            ["results", "推演结果"],
            ["compare", "方案对比"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={view === id ? "tab active" : "tab"}
            onClick={() => setView(id)}
          >
            {label}
          </button>
        ))}
        <span className="spacer" />
        <button type="button" className="ghost" onClick={undo} disabled={busy}>
          撤销
        </button>
        <button type="button" className="ghost" onClick={() => setPlanOpen(true)} disabled={busy}>
          帮我生成布局
        </button>
      </nav>

      {view === "layout" ? (
        <div className="body">
          <aside className="library">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索设备"
              aria-label="搜索设备"
            />
            {CATEGORIES.map((category) => (
              <section key={category}>
                <h2>{category}</h2>
                {filtered
                  .filter((item) => item.category === category)
                  .map((item) => (
                    <button
                      key={item.typeElementId}
                      type="button"
                      className={armed?.typeElementId === item.typeElementId ? "lib on" : "lib"}
                      onClick={() => setArmed(item)}
                    >
                      <span>{item.name}</span>
                      <small>
                        {item.typeElementId} · {item.footprintW}×{item.footprintD} m
                      </small>
                    </button>
                  ))}
              </section>
            ))}
            <p className="hint">目录与派生器缺省 footprint 一致，盒子代理，不是生产 GLB。</p>
          </aside>

          <section className="stage">
            <div className="toolbar">
              <button type="button" onClick={applyTemplate} disabled={busy}>
                使用矩形模板
              </button>
              <button
                type="button"
                onClick={() => armed && place(armed, widthM / 2, depthM / 2)}
                disabled={!armed || busy}
              >
                放到场地中心
              </button>
              <button type="button" onClick={() => void onPlan()} disabled={busy}>
                帮我生成布局
              </button>
              <span className="spacer" />
              <button type="button" className="primary" onClick={() => void onPrepare()} disabled={busy}>
                校验并准备
              </button>
              <button type="button" className="primary" onClick={() => void onSimulate()} disabled={busy}>
                开始推演
              </button>
            </div>
            <svg
              className={armed ? "canvas armed" : "canvas"}
              viewBox={`0 0 ${widthM} ${depthM}`}
              onClick={onCanvasClick}
              role="img"
              aria-label="布局画布，北在上，单位米"
            >
              <rect x={0} y={0} width={widthM} height={depthM} className="floor" />
              <line
                x1={2}
                y1={depthM - aisleYM}
                x2={Math.max(widthM - 2, 2)}
                y2={depthM - aisleYM}
                className="aisle"
                strokeWidth={aisleWidthM}
              />
              {elements.map((el) => {
                const w = el.params.footprintW ?? libraryItem(el.typeElementId)?.footprintW ?? 1;
                const d = el.params.footprintD ?? libraryItem(el.typeElementId)?.footprintD ?? 1;
                const active = el.instanceId === selectedId;
                return (
                  <g
                    key={el.instanceId}
                    transform={`translate(${el.x} ${depthM - el.y}) rotate(${-el.yawDeg})`}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (armed) return;
                      setSelectedId(el.instanceId);
                    }}
                  >
                    <rect
                      x={-w / 2}
                      y={-d / 2}
                      width={w}
                      height={d}
                      className={active ? "eq on" : "eq"}
                    />
                    <text className="eq-label" y={4}>
                      {libraryItem(el.typeElementId)?.name ?? el.typeElementId}
                    </text>
                  </g>
                );
              })}
            </svg>
            <footer className="statusbar">
              <span>{statusNote}</span>
              <span>
                {elements.length} 个设备 · 通道 {aisleWidthM} m · {armed ? `放置 ${armed.name}` : "选择设备后点击画布"}
              </span>
            </footer>
          </section>

          <aside className="inspector">
            {selected ? (
              <>
                <h2>{libraryItem(selected.typeElementId)?.name ?? selected.typeElementId}</h2>
                <p className="hint">{selected.instanceId}</p>
                {(["x", "y", "yawDeg"] as const).map((key) => (
                  <label key={key}>
                    {key === "yawDeg" ? "朝向 °" : key === "x" ? "X 东 (m)" : "Y 北 (m)"}
                    <input
                      type="number"
                      step="0.1"
                      value={selected[key]}
                      onChange={(event) =>
                        updateSelected({ [key]: Number(event.target.value) } as Partial<PlacedElement>)
                      }
                    />
                  </label>
                ))}
                {Object.entries(selected.params).map(([key, value]) => (
                  <label key={key}>
                    {key}
                    <input
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(event) =>
                        updateSelected(
                          {},
                          {
                            ...selected.params,
                            [key]: Number(event.target.value),
                          },
                        )
                      }
                    />
                  </label>
                ))}
                <button type="button" className="danger" onClick={() => removeSelected(selected.instanceId)}>
                  删除设备
                </button>
              </>
            ) : (
              <>
                <h2>场地与推演输入</h2>
                <label>
                  场地宽 X (m)
                  <input
                    type="number"
                    min={4}
                    step="0.5"
                    value={widthM}
                    onChange={(event) => {
                      setWidthM(Number(event.target.value));
                      setDirty(true);
                    }}
                  />
                </label>
                <label>
                  场地深 Y (m)
                  <input
                    type="number"
                    min={4}
                    step="0.5"
                    value={depthM}
                    onChange={(event) => {
                      setDepthM(Number(event.target.value));
                      setDirty(true);
                    }}
                  />
                </label>
                <label>
                  主通道宽 (m)
                  <input
                    type="number"
                    min={0.5}
                    step="0.1"
                    value={aisleWidthM}
                    onChange={(event) => {
                      setAisleWidthM(Number(event.target.value));
                      setDirty(true);
                    }}
                  />
                </label>
                <label>
                  主通道 Y (m)
                  <input
                    type="number"
                    step="0.5"
                    value={aisleYM}
                    onChange={(event) => {
                      setAisleYM(Number(event.target.value));
                      setDirty(true);
                    }}
                  />
                </label>
                <label>
                  出库托数（推演输入）
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={outboundQty}
                    onChange={(event) => setOutboundQty(Number(event.target.value))}
                  />
                </label>
                <label>
                  叉车数量（推演输入）
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={forkliftCount}
                    onChange={(event) => setForkliftCount(Number(event.target.value))}
                  />
                </label>
                <p className="hint">这些是提交给 DES 的输入。吞吐、等待、利用率和瓶颈只在跑完后显示。</p>
              </>
            )}
            <h2>校验</h2>
            {!prepare ? <p className="hint">尚未准备。</p> : null}
            {prepare?.simulationReady ? <p className="ok">simulationReady · {prepare.layoutRevision}</p> : null}
            {failedChecks.map((check) => (
              <p key={check.ruleId} className={check.status === "fail" ? "bad" : "warntext"}>
                {check.status} · {check.message}
              </p>
            ))}
            <h2>复杂识图</h2>
            <label>
              能力
              <select value={recCapability} onChange={(event) => setRecCapability(event.target.value)}>
                <option value="dxf_vector_extract">DXF 矢量提取</option>
                <option value="ocr_assist">OCR 辅助</option>
                <option value="polygon_height_partition">多边形/高度分区</option>
              </select>
            </label>
            <label>
              文件名（不上传内容）
              <input value={recFile} onChange={(event) => setRecFile(event.target.value)} />
            </label>
            <button type="button" onClick={() => void onRecognize()} disabled={busy}>
              尝试识别
            </button>
            {recognition ? (
              <div className="failcard">
                <strong>
                  {recognition.status} · {recognition.code}
                </strong>
                <p>{recognition.message}</p>
                <p>{recognition.correction}</p>
              </div>
            ) : (
              <p className="hint">识别不会生成精确场地，也不会把高置信度当成已确认。</p>
            )}
          </aside>
        </div>
      ) : null}

      {view === "results" ? (
        <section className="sheet">
          <h2>单方案四卡</h2>
          <p className="hint">四卡来自本次跑次的事件，不是界面公式。</p>
          {dirty && sim ? <p className="warntext">布局已改，下面仍是上一跑次 {sim.layoutRevision}。</p> : null}
          {!sim ? <p>还没有跑次。在布局工作台保存并准备后开始推演。</p> : null}
          {sim ? (
            <>
              <p className="hint">
                run {sim.runId} · layoutRevision {sim.layoutRevision} · 完成率 {fmt(sim.completionRate)} · 完成{" "}
                {sim.completedTasks ?? "—"} / 未完成 {sim.incompleteTasks ?? "—"}
              </p>
              <div className="cards">
                <article>
                  <h3>吞吐</h3>
                  <p className="kpi">{fmt(sim.cards.throughput?.value, 3)}</p>
                  <p>{sim.cards.throughput?.unit ?? "palletEq/h"}</p>
                  <p>外部发运 {sim.cards.throughput?.outboundPalletEq ?? "—"} 托当量</p>
                </article>
                <article>
                  <h3>等待</h3>
                  <p className="kpi">{fmt(sim.cards.wait?.meanSec, 1)}</p>
                  <p>
                    均值秒 · P95 {fmt(sim.cards.wait?.p95Sec, 1)}
                    {sim.cards.wait?.p95Meta?.sampleInsufficient ? "（样本不足，不报 P95）" : ""}
                  </p>
                  <p>样本 {sim.cards.wait?.sampleCount ?? "—"}</p>
                </article>
                <article>
                  <h3>利用率</h3>
                  <p className="kpi">{fmt(sim.cards.utilization?.value, 3)}</p>
                  <p>{sim.cards.utilization?.unit ?? "ratio"}</p>
                  <p>{sim.cards.utilization?.note ?? ""}</p>
                </article>
                <article>
                  <h3>瓶颈</h3>
                  <p className="kpi small">{sim.cards.bottleneck?.top1?.entityId ?? "—"}</p>
                  <p>{sim.cards.bottleneck?.top1?.note ?? `等待 ${fmt(sim.cards.bottleneck?.top1?.waitSec, 1)} s`}</p>
                </article>
              </div>
              {sim.warnings.length ? <p className="hint">警告：{sim.warnings.join("、")}</p> : null}
              {saved && sim.layoutRevision !== saved.layoutRevision ? (
                <p className="warntext">下面是跑次 {sim.layoutRevision}，当前保存的修订是 {saved.layoutRevision}。</p>
              ) : null}
              <button type="button" className="primary" onClick={() => void onCostCompare()} disabled={busy || dirty}>
                估算成本并对比叉车加一
              </button>
              <button type="button" onClick={() => setView("layout")}>
                回到布局修改
              </button>
            </>
          ) : null}
        </section>
      ) : null}

      {view === "compare" ? (
        <section className="sheet">
          <h2>方案对比</h2>
          <p className="hint">
            表和雷达开关来自 /comparisons。价目是 demo 输入（demoOnly），不是界面公式。没有 completedCycleMeanSec 时周期留空，不用等待均值填上。
          </p>
          <button type="button" className="primary" onClick={() => void onCostCompare()} disabled={busy || dirty || !sim}>
            用当前跑次对比叉车加一
          </button>
          {!compare ? <p>还没有比较。先在推演结果里跑完四卡。</p> : null}
          {compare?.kpiFromUiDemo ? <p className="bad">接口标记了界面公式，这张表不能当结果。</p> : null}
          {compare && !compare.kpiFromUiDemo ? (
            <>
              <p className="hint">
                {compare.id} · {compare.mode}
                {compare.radarEnabled ? " · 雷达已开" : " · 雷达关闭，只显示表格"}
              </p>
              <p className="hint">{compare.radarNote}</p>
              {compare.issues.map((line) => (
                <p key={line} className="warntext">
                  {line}
                </p>
              ))}
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>方案</th>
                    <th>库容</th>
                    <th>周期 s</th>
                    <th>吞吐</th>
                    <th>等待 s</th>
                    <th>初投</th>
                    <th>成本</th>
                    <th>资源</th>
                  </tr>
                </thead>
                <tbody>
                  {compare.rows.map((row) => (
                    <tr key={`${row.runId ?? ""}-${row.label ?? ""}`}>
                      <td>
                        {row.label ?? "—"}
                        <div className="hint">{row.layoutRevision}</div>
                      </td>
                      <td>{fmt(row.effectiveCapacity, 1)}</td>
                      <td>{fmt(row.completedCycleMeanSec, 1)}</td>
                      <td>{fmt(row.outboundThroughput, 3)}</td>
                      <td>{fmt(row.waitMeanSec, 1)}</td>
                      <td>{fmt(row.capex, 0)}</td>
                      <td>{row.costStatus ?? "—"}</td>
                      <td>{fingerprintText(row.resourceFingerprint)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {compare.radarEnabled
                ? compare.series.map((series) => (
                    <p key={series.entryId ?? series.label}>
                      {series.label}：
                      {(series.points ?? [])
                        .map((point) => `${point.axisId}=${point.score === null ? "null" : point.score}`)
                        .join(" · ")}
                    </p>
                  ))
                : null}
            </>
          ) : null}
        </section>
      ) : null}

      {error ? <p className="banner">{error}</p> : null}
      {busy ? <p className="banner quiet">请求中…</p> : null}

      {planOpen ? (
        <div className="drawer-back" onClick={() => setPlanOpen(false)}>
          <div className="drawer" onClick={(event) => event.stopPropagation()}>
            <h2>帮我生成布局</h2>
            <p className="hint">可选入口。生成新候选，不覆盖当前方案。评价级别 quick，不是运营效率验证。</p>
            <button type="button" className="primary" onClick={() => void onPlan()} disabled={busy}>
              按容量目标生成
            </button>
            {disabledGoals.length ? (
              <ul>
                {disabledGoals.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
            {planOutcome ? <p>结果：{planOutcome}</p> : null}
            {candidates.length === 0 && planOutcome ? <p>本次没有可用候选，不会凑数。</p> : null}
            {candidates.map((candidate) => {
              const cap = candidate.metrics?.geometricPalletCapacity;
              return (
                <article key={candidate.id} className="cand">
                  <strong>{candidate.id}</strong>
                  <p>
                    {candidate.evaluationLevel} · 几何库容 {cap?.value ?? "—"} {cap?.unit ?? ""}（估算）
                  </p>
                  <p className="hint">
                    {candidate.claimsOperationalEfficiency ? "异常：宣称了运营效率" : "未宣称运营效率"}
                  </p>
                  <button type="button" onClick={() => void adopt(candidate.id)} disabled={busy}>
                    采用并编辑
                  </button>
                </article>
              );
            })}
            <button type="button" className="ghost" onClick={() => setPlanOpen(false)}>
              关闭
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
