import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://217.142.246.70:8000',
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

export default api
