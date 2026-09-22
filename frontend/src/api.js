const BASE = "/api";

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: options.body && !(options.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : undefined,
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(Array.isArray(detail) ? JSON.stringify(detail) : String(detail));
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  listProjects: () => req("/projects"),
  createProject: (name) =>
    req("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  getProject: (id) => req(`/projects/${id}`),
  deleteProject: (id) => req(`/projects/${id}`, { method: "DELETE" }),
  createDemo: () => req("/projects/demo", { method: "POST" }),

  importTranscript: (pid, payload) =>
    req(`/projects/${pid}/import`, { method: "POST", body: JSON.stringify(payload) }),
  importExport: (data, name) =>
    req("/projects/import_export", {
      method: "POST",
      body: JSON.stringify({ data, name: name || null }),
    }),
  exportUrl: (pid) => `${BASE}/projects/${pid}/export`,

  uploadAudio: (pid, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req(`/projects/${pid}/audio`, { method: "POST", body: fd });
  },
  audioUrl: (pid) => `${BASE}/projects/${pid}/audio?t=${Date.now()}`,

  createAnnotation: (pid, data) =>
    req(`/projects/${pid}/annotations`, { method: "POST", body: JSON.stringify(data) }),
  updateAnnotation: (pid, aid, data) =>
    req(`/projects/${pid}/annotations/${aid}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteAnnotation: (pid, aid) =>
    req(`/projects/${pid}/annotations/${aid}`, { method: "DELETE" }),

  startMerge: (pid, a, b, name) =>
    req(`/projects/${pid}/merge`, {
      method: "POST",
      body: JSON.stringify({ a, b, name: name || null }),
    }),
  getMerge: (mid) => req(`/merges/${mid}`),
  resolve: (mid, conflictId, choice, custom) =>
    req(`/merges/${mid}/resolve`, {
      method: "POST",
      body: JSON.stringify({ conflict_id: conflictId, choice, custom: custom || null }),
    }),
  finalizeMerge: (mid) => req(`/merges/${mid}/finalize`, { method: "POST" }),
};

export async function readJsonFile(file) {
  const text = await file.text();
  return JSON.parse(text);
}

export async function downloadExport(pid, filename) {
  const res = await fetch(api.exportUrl(pid));
  if (!res.ok) throw new Error("导出失败");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "export.json";
  a.click();
  URL.revokeObjectURL(url);
}
