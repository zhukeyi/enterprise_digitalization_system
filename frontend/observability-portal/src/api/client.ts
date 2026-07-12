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

  getRagDocs: (page = 1, pageSize = 20) => fetchJSON(`/rag/docs?page=${page}&page_size=${pageSize}`),
  getTraces: (page = 1, pageSize = 20) => fetchJSON(`/traces?page=${page}&page_size=${pageSize}`),
  getAuditLogs: (page = 1, pageSize = 20) => fetchJSON(`/audit/logs?page=${page}&page_size=${pageSize}`),
  retrieveRag: (query: string, topK = 10) => postJSON("/rag/debug/retrieve", { query, top_k: topK }),
};

