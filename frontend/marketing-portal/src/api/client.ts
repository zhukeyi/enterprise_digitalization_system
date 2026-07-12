import axios from 'axios'

const client = axios.create({
  baseURL: '/fde-api',
  timeout: 60000,
})

export interface MarketingOverview {
  total_brands: number
  avg_geo_index: number
  total_keywords: number
  tracked_engines: number
  total_ad_spend: number
  blended_roas: number
  total_content: number
  avg_eeat: number
  top_opportunities: {
    brand: string
    brand_id: string
    keyword: string
    opportunity_score: number
    monthly_volume: number
    difficulty: number
  }[]
  engine_breakdown: { engine: string; avg_score: number; brands_cited: number }[]
}

export interface Brand {
  brand_id: string
  name: string
  domain: string
  category: string
  strength: number
}

export interface EngineVisibility {
  engine: string
  score: number
  cited: boolean
  avg_position: number
  sampled_keywords: number
}

export interface BrandVisibility {
  brand_id: string
  brand_name: string
  geo_index: number
  engines: EngineVisibility[]
  cited_keywords: number
  total_keywords: number
  trend_30d: number
}

export interface KeywordOpportunity {
  term: string
  intent: string
  monthly_volume: number
  difficulty: number
  current_position: number
  opportunity_score: number
}

export interface ContentScore {
  eeat_score: number
  experience: number
  expertise: number
  authoritativeness: number
  trustworthiness: number
  citation_score: number
  suggestions: string[]
}

export interface ContentPiece {
  title: string
  body: string
  topic: string
  eeat_score: number
  citation_score: number
  geo_optimized: boolean
}

export interface AdVariant {
  variant_id: string
  headline: string
  body: string
  cta: string
  quality_score: number
  predicted_ctr: number
  angle: string
}

export interface ABTestResult {
  variant_a: string
  variant_b: string
  impressions_a: number
  impressions_b: number
  clicks_a: number
  clicks_b: number
  ctr_a: number
  ctr_b: number
  lift_pct: number
  z_score: number
  p_value: number
  confidence: number
  winner: string | null
  significant: boolean
}

export interface BudgetAllocation {
  allocations: {
    platform: string
    current_spend: number
    current_roas: number
    allocated_budget: number
    projected_revenue: number
    projected_roas: number
  }[]
  blended_roas: number
  even_split_roas: number
  projected_revenue: number
  uplift_pct: number
}

export interface ROIPrediction {
  spend: number
  predicted_revenue: number
  predicted_roas: number
  predicted_profit: number
  payback_ratio: number
  confidence: number
  slope: number
  fit_r_squared: number
}

export interface PlatformPerformanceAgg {
  blended_roas: number
  total_spend: number
  total_revenue: number
  total_impressions: number
  total_clicks: number
  total_conversions: number
  blended_ctr: number
  blended_conv_rate: number
  ranking: {
    platform: string
    roas: number
    spend: number
    revenue: number
    trend_30d: number
  }[]
}

export async function getOverview(): Promise<MarketingOverview> {
  const { data } = await client.get<MarketingOverview>('/api/marketing/overview')
  return data
}

export async function getBrands(): Promise<Brand[]> {
  const { data } = await client.get<Brand[]>('/api/marketing/brands')
  return data
}

export async function getVisibility(brandId: string): Promise<BrandVisibility> {
  const { data } = await client.get<BrandVisibility>(`/api/marketing/visibility/${brandId}`)
  return data
}

export async function getKeywords(brandId: string): Promise<KeywordOpportunity[]> {
  const { data } = await client.get<KeywordOpportunity[]>(`/api/marketing/keywords/${brandId}`)
  return data
}

export async function optimizeContent(payload: { title: string; body: string }): Promise<ContentScore> {
  const { data } = await client.post<ContentScore>('/api/marketing/content/optimize', payload)
  return data
}

export async function generateGEO(payload: { brand: string; topic: string }): Promise<ContentPiece> {
  const { data } = await client.post<ContentPiece>('/api/marketing/content/geo', payload)
  return data
}

export async function generateSEO(payload: { brand: string; topic: string }): Promise<ContentPiece> {
  const { data } = await client.post<ContentPiece>('/api/marketing/content/seo', payload)
  return data
}

export async function generateAds(payload: { brand: string; topic: string; area?: string; n_variants?: number }) {
  const { data } = await client.post('/api/marketing/ads/generate', payload)
  return data
}

export async function abTest(payload: {
  variant_a: string
  variant_b: string
  impressions_a: number
  clicks_a: number
  impressions_b: number
  clicks_b: number
}): Promise<ABTestResult> {
  const { data } = await client.post<ABTestResult>('/api/marketing/ads/abtest', payload)
  return data
}

export async function allocateBudget(payload: { brand_id: string; total_budget: number }): Promise<BudgetAllocation> {
  const { data } = await client.post<BudgetAllocation>('/api/marketing/ads/budget', payload)
  return data
}

export async function predictROI(payload: { brand_id: string; spend: number }): Promise<ROIPrediction> {
  const { data } = await client.post<ROIPrediction>('/api/marketing/roi/predict', payload)
  return data
}

export async function getPerformance(brandId: string): Promise<PlatformPerformanceAgg> {
  const { data } = await client.get<PlatformPerformanceAgg>(`/api/marketing/performance/${brandId}`)
  return data
}
