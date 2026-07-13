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

export async function collectIntelligence(params: {
  source_type?: string
  query?: string
  url?: string
  max_items?: number
}): Promise<{ success: boolean; items_collected: number; error?: string; items?: IntelItem[] }> {
  const { data } = await client.post('/api/intelligence/collect', params)
  return data
}

// ══════════════════════════════════════════════════════════════════
// Customs trade data base (P1-C, C-6)
// ══════════════════════════════════════════════════════════════════

export interface TradeRecord {
  id: string
  hs_code: string
  hs_description: string
  reporter_country: string
  partner_country: string
  port: string
  trade_flow: string
  value_usd: number
  quantity: number | null
  quantity_unit: string | null
  year: number
  period: string
  tier: string
  provider: string
  collected_at: string
}

export interface BuyerEntity {
  id: string
  raw_name: string
  normalized_name: string
  country: string | null
  source_country: string | null
  import_count: number
  total_value_usd: number
  top_hs_codes: string[]
  top_ports: string[]
  first_seen: string | null
  last_seen: string | null
}

export interface CustomsOverview {
  trade_record_count: number
  buyer_count: number
  tier1_available: boolean
  tier2_available: boolean
  note: string
}

export interface TrendPoint {
  bucket: string
  value_usd: number
  quantity: number | null
  records: number
}

export interface IngestRequest {
  provider: string
  url?: string
  reporter?: string
  partner?: string
  year?: string
  hs_code?: string
  max_items?: number
}

export interface IngestResponse {
  provider: string
  tier: string
  stored: number
  error?: string | null
}

export async function getCustomsOverview(): Promise<CustomsOverview> {
  const { data } = await client.get<CustomsOverview>('/api/customs/overview')
  return data
}

export async function getTradeRecords(params: {
  hs_code?: string
  reporter_country?: string
  partner_country?: string
  port?: string
  limit?: number
} = {}): Promise<TradeRecord[]> {
  const { data } = await client.get<TradeRecord[]>('/api/customs/trade-records', { params })
  return data
}

export async function getBuyers(params: { country?: string; limit?: number } = {}): Promise<BuyerEntity[]> {
  const { data } = await client.get<BuyerEntity[]>('/api/customs/buyers', { params })
  return data
}

export async function getCustomsTrends(hs_code: string, group_by = 'year'): Promise<TrendPoint[]> {
  const { data } = await client.get<TrendPoint[]>('/api/customs/trends', {
    params: { hs_code, group_by },
  })
  return data
}

export async function ingestCustoms(req: IngestRequest): Promise<IngestResponse> {
  const { data } = await client.post<IngestResponse>('/api/customs/ingest', req)
  return data
}
