import axios from 'axios'
import { getApiBase } from '../mapai/runtime'

const api = axios.create({
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

/** 每次请求前刷新 baseURL（支持运行时覆盖后端地址） */
function req() {
  api.defaults.baseURL = getApiBase()
  return api
}

// Chat completions (OpenAI-compatible)
export async function chatCompletion(messages: { role: string; content: string }[]) {
  return req().post('/v1/chat/completions', { messages })
}

// RAG search
export async function ragSearch(query: string, topK = 5) {
  return req().post('/orchestrator/search', { query, top_k: topK })
}

// Health check
export async function healthCheck() {
  return req().get('/health')
}

// Map analysis — POST /map/analysis (M3-T9/M3-T10)
export async function submitMapAnalysis(
  entityIds: string[],
  method?: string,
  query?: string,
) {
  return req().post('/map/analysis', { entity_ids: entityIds, method, query })
}

// Map spatial correlation — POST /map/correlate
export async function correlateEntities(
  entityIds: string[],
  method?: string,
) {
  return req().post('/map/correlate', { entity_ids: entityIds, method })
}

// Map regions list — GET /map/regions
export async function getMapRegions() {
  return req().get('/map/regions')
}

export default api
