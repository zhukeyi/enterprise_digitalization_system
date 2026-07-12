import axios from 'axios'

const client = axios.create({
  baseURL: '/fde-api',
  timeout: 60000,
})

export interface OverviewStats {
  total_items: number
  total_sources: number
  source_types: { name: string; count: number }[]
  recent_items: IntelItem[]
  daily_collection: { date: string; count: number }[]
  sentiment_distribution: { positive: number; neutral: number; negative: number }
}

export interface IntelItem {
  id: string
  title: string
  source: string
  url?: string
  summary: string
  sentiment: string
  keywords: string[]
  collected_at: string
  language?: string
}

export interface SourceInfo {
  source_type: string
  url: string
  max_items: number
  label: string
  active: boolean
}

export interface TrendItem {
  date: string
  count: number
  keywords: string[]
}

export async function getOverview(): Promise<OverviewStats> {
  const { data } = await client.get<OverviewStats>('/api/intelligence/overview')
  return data
}

export async function getSources(): Promise<SourceInfo[]> {
  const { data } = await client.get<SourceInfo[]>('/api/intelligence/sources')
  return data
}

export async function getItems(limit = 50): Promise<IntelItem[]> {
  const { data } = await client.get<IntelItem[]>(`/api/intelligence/items?limit=${limit}`)
  return data
}

export async function getTrends(days = 7): Promise<TrendItem[]> {
  const { data } = await client.get<TrendItem[]>(`/api/intelligence/trends?days=${days}`)
  return data
}
