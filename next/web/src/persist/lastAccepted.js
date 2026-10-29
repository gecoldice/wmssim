/** Last server-accepted project pointer. Drafts are not stored here. */

export const ACCEPTED_KEY = "next.slice.lastAccepted.v1";

export function rememberAccepted(storage, record) {
  storage.setItem(
    ACCEPTED_KEY,
    JSON.stringify({
      projectId: record.projectId,
      layoutId: record.layoutId,
    }),
  );
}

export function readAccepted(storage) {
  const raw = storage.getItem(ACCEPTED_KEY);
  if (!raw) return null;
  try {
    const data = JSON.parse(raw);
    if (!data || typeof data.projectId !== "string" || typeof data.layoutId !== "string") return null;
    return { projectId: data.projectId, layoutId: data.layoutId };
  } catch {
    return null;
  }
}

export function clearAccepted(storage) {
  storage.removeItem(ACCEPTED_KEY);
}
