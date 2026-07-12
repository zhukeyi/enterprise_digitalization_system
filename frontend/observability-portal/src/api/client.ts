const BASE = "/fde-api/api/observability";

async function fetchJSON<T = any>(url: string): Promise<T> {
  const resp = await fetch(`${BASE}${url}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${url}`);
  return resp.json();
}

async function postJSON<T = any>(url: string, body: any): Promise<T> {
  const resp = await fetch(`${BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${url}`);
  return resp.json();
}

export const api = {
  getOverview: () => fetchJSON("/overview"),
  getReadyz: () => fetchJSON("/readyz"),
  getHealthz: () => fetchJSON("/healthz"),
  getLivez: () => fetchJSON("/livez"),
  getComponents: () => fetchJSON("/health/components"),
  getServiceMap: () => fetchJSON("/health/service-map"),
  getEndpoints: () => fetchJSON("/api/endpoints"),
  getApiStats: (path?: string) => fetchJSON(`/api/stats${path ? `?path=${encodeURIComponent(path)}` : ""}`),

  // Phase 2: Token router
  getTokenUsage: (groupBy = "model", hours = 24) => fetchJSON(`/tokens/usage?group_by=${groupBy}&hours=${hours}`),
  getTokenCost: (period = "daily") => fetchJSON(`/tokens/cost?period=${period}`),
  getTokenRouting: () => fetchJSON("/tokens/routing"),
  getTokenFailover: () => fetchJSON("/tokens/failover"),
  getBudget: (agentModule?: string) => fetchJSON(`/tokens/budget${agentModule ? `?agent_module=${agentModule}` : ""}`),
  setBudget: (agentModule: string, dailyLimitUsd: number) => postJSON("/tokens/budget", { agent_module: agentModule, daily_limit_usd: dailyLimitUsd }),
  getBudgetEvents: (hours = 24) => fetchJSON(`/tokens/budget/events?hours=${hours}`),

  // Phase 2: API management
  getExternalApis: () => fetchJSON("/api/external"),
  getApiKeys: () => fetchJSON("/api/keys"),
  createApiKey: (body: any) => postJSON("/api/keys", body),
  updateApiKey: (keyId: string, body: any) => {
    return fetch(`${BASE}/api/keys/${keyId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => r.json());
  },
  deleteApiKey: (keyId: string) => {
    return fetch(`${BASE}/api/keys/${keyId}`, { method: "DELETE" }).then((r) => r.json());
  },

  getRagDocs: (page = 1, pageSize = 20, docType?: string, source?: string) => {
    const qs: string[] = [`page=${page}`, `page_size=${pageSize}`];
    if (docType) qs.push(`doc_type=${encodeURIComponent(docType)}`);
    if (source) qs.push(`source=${encodeURIComponent(source)}`);
    return fetchJSON(`/rag/docs?${qs.join("&")}`);
  },
  getRagDocChunks: (docId: string, page = 1, pageSize = 50) =>
    fetchJSON(`/rag/docs/${docId}/chunks?page=${page}&page_size=${pageSize}`),
  getRagChunkDetail: (chunkId: string) => fetchJSON(`/rag/chunks/${chunkId}`),
  deleteRagDoc: (docId: string) => {
    return fetch(`${BASE}/rag/docs/${docId}?confirm=DELETE`, { method: "DELETE" }).then((r) => r.json());
  },
  reindexRagDoc: (docId: string) => postJSON(`/rag/docs/${docId}/reindex`, {}),
  getTraces: (page = 1, pageSize = 20, service?: string, status?: string) => {
    const qs: string[] = [`page=${page}`, `page_size=${pageSize}`];
    if (service) qs.push(`service=${encodeURIComponent(service)}`);
    if (status) qs.push(`status=${encodeURIComponent(status)}`);
    return fetchJSON(`/traces?${qs.join("&")}`);
  },
  getTraceStats: () => fetchJSON("/traces/stats"),
  getTraceDetail: (traceId: string) => fetchJSON(`/traces/${traceId}`),
  getAuditLogs: (page = 1, pageSize = 20, filters?: Record<string, string>) => {
    const qs: string[] = [`page=${page}`, `page_size=${pageSize}`];
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        if (v) qs.push(`${k}=${encodeURIComponent(v)}`);
      }
    }
    return fetchJSON(`/audit/logs?${qs.join("&")}`);
  },
  exportAudit: (filters?: Record<string, string>) => {
    const qs: string[] = ["format=csv"];
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        if (v) qs.push(`${k}=${encodeURIComponent(v)}`);
      }
    }
    return fetch(`${BASE}/audit/export?${qs.join("&")}`).then((r) => r.text());
  },
  getAlerts: (page = 1, pageSize = 50, severity?: string) => {
    const qs: string[] = [`page=${page}`, `page_size=${pageSize}`];
    if (severity) qs.push(`severity=${severity}`);
    return fetchJSON(`/alerts?${qs.join("&")}`);
  },
  evaluateAlerts: () => postJSON("/alerts/evaluate", {}),
  getAlertRules: () => fetchJSON("/alerts/rules"),
  setAlertRule: (body: any) => postJSON("/alerts/rules", body),
  deleteAlertRule: (ruleId: string) => {
    return fetch(`${BASE}/alerts/rules/${ruleId}`, { method: "DELETE" }).then((r) => r.json());
  },
  getDrift: () => fetchJSON("/drift"),
  retrieveRag: (query: string, topK = 10, docType?: string) =>
    postJSON("/rag/debug/retrieve", { query, top_k: topK, doc_type: docType }),
};

