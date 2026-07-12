import axios from 'axios'

// 相对 baseURL：浏览器同源经 nginx 转发 → /fde-api/ 去前缀到后端 :8000
const client = axios.create({
  baseURL: '/fde-api',
  timeout: 60000,
})

export interface AskSource {
  id?: string
  title?: string
  text?: string
  doc_type?: string
  [key: string]: unknown
}

export interface AskResult {
  query: string
  answer: string
  count: number
  sources: AskSource[]
}

export interface UploadResult {
  doc_type?: string
  source_ref?: string
  rows?: number
  canonical?: number
  indexed_vectors?: number
  raw_id?: string
  [key: string]: unknown
}

export async function uploadExcel(file: File, docType = 'excel_upload'): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', docType)
  const { data } = await client.post<UploadResult>('/ingest/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function askData(
  query: string,
  docType: string | null = null,
  topK = 5,
): Promise<AskResult> {
  const { data } = await client.post<AskResult>('/api/data/ask', {
    query,
    doc_type: docType,
    top_k: topK,
  })
  return data
}

// ══════════════════════════════════════════════════════════════════
// Dashboard API (V5-②)
// ══════════════════════════════════════════════════════════════════

export interface DocTypeItem {
  name: string
  count: number
}

export interface RecentUpload {
  id: string
  title: string
  doc_type: string
  created_at: string | null
}

export interface DailyIngest {
  date: string
  count: number
}

export interface DashboardStats {
  total_documents: number
  total_chunks: number
  total_raw: number
  doc_types: DocTypeItem[]
  recent_uploads: RecentUpload[]
  daily_ingest: DailyIngest[]
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await client.get<DashboardStats>('/api/dashboard/stats')
  return data
}
