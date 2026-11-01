/** Slice HTTP client. Paths are only the manual-slice endpoints. */

export const requestLog: string[] = [];

export type ApiResult = { status: number; data: Record<string, unknown> };

async function send(method: string, path: string, body?: unknown): Promise<ApiResult> {
  requestLog.push(`${method} ${path}`);
  const response = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  return { status: response.status, data };
}

export function createProject(name: string) {
  return send("POST", "/api/v1/projects", { name, unitSystem: "metric" });
}

export function getProject(projectId: string) {
  return send("GET", `/api/v1/projects/${projectId}`);
}

export function saveFacility(projectId: string, facility: unknown, baseRevision: string | null) {
  return send("POST", `/api/v1/projects/${projectId}/facility-revisions`, {
    facility,
    baseRevision,
  });
}

export function getFacility(projectId: string) {
  return send("GET", `/api/v1/projects/${projectId}/facility`);
}

export function saveLayout(layoutId: string, projectId: string, baseRevision: string | null, document: unknown) {
  return send("POST", `/api/v1/layouts/${layoutId}/revisions`, {
    projectId,
    baseRevision,
    document,
  });
}

export function getLayout(layoutId: string) {
  return send("GET", `/api/v1/layouts/${layoutId}`);
}

export function startPrepare(layoutId: string, revision: string) {
  return send("POST", `/api/v1/layouts/${layoutId}/prepare-jobs`, {
    layoutRef: { id: layoutId, revision },
  });
}

export function startSimulation(body: unknown) {
  return send("POST", "/api/v1/simulation-jobs", body);
}

export function getRun(runId: string) {
  return send("GET", `/api/v1/runs/${runId}`);
}

export async function pollJob(jobId: string): Promise<ApiResult> {
  for (let i = 0; i < 80; i += 1) {
    const result = await send("GET", `/api/v1/jobs/${jobId}`);
    const status = result.data.status;
    if (status === "succeeded" || status === "failed") return result;
    await new Promise((resolve) => setTimeout(resolve, 40));
  }
  return { status: 504, data: { code: "COMPUTATION_FAILED", message: "任务没有在预期时间内结束" } };
}
