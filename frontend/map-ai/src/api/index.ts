import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/fde-api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Chat completions (OpenAI-compatible)
export async function chatCompletion(messages: { role: string; content: string }[]) {
  return api.post('/v1/chat/completions', { messages })
}

// RAG search
export async function ragSearch(query: string, topK = 5) {
  return api.post('/orchestrator/search', { query, top_k: topK })
}

// Health check
export async function healthCheck() {
  return api.get('/health')
}

// Map analysis — POST /map/analysis (M3-T9/M3-T10)
export async function submitMapAnalysis(
  entityIds: string[],
  method?: string,
  query?: string,
) {
  return api.post('/map/analysis', { entity_ids: entityIds, method, query })
}

// Map spatial correlation — POST /map/correlate
export async function correlateEntities(
  entityIds: string[],
  method?: string,
) {
  return api.post('/map/correlate', { entity_ids: entityIds, method })
}

// Map regions list — GET /map/regions
export async function getMapRegions() {
  return api.get('/map/regions')
}

export default api
