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

// ══════════════════════════════════════════════════════════════════
// Customs → GEO campaign (P1-C, C-8~C-12)
// ══════════════════════════════════════════════════════════════════

export interface DeliverableBuyer {
  name: string
  country: string | null
  source_country: string | null
  total_value_usd: number
  import_count: number
  top_hs_codes: string[]
  top_ports: string[]
}

export interface CustomsSegment {
  segment_id: string
  name: string
  category: string
  hs_codes: string[]
  port: string
  frequency_tier: string
  growth_tier: string
  buyer_count: number
  deliverable_count: number
  blocked_count: number
  total_value_usd: number
  deliverable_buyers: DeliverableBuyer[]
  blocked_sample: string[]
  compliance_status: string
  created_at: string
}

export interface CustomsOverview {
  total_segments: number
  outreach_ready: number
  blocked_segments: number
  partial_segments: number
  total_deliverable_buyers: number
  total_blocked_buyers: number
  total_deliverable_value_usd: number
}

export interface CustomsContent {
  segment_id: string
  topic: string
  geo_piece: {
    title: string
    body: string
    topic: string
    eeat_score: number
    citation_score: number
    geo_optimized: boolean
  }
  multilingual: {
    brand: string
    topic: string
    source_lang: string
    target_langs: string[]
    pieces: Record<string, { title: string; body: string; geo_optimized: boolean }>
  }
  keywords: {
    term: string
    intent: string
    monthly_volume: number
    difficulty: number
    current_position: number
    opportunity_score: number
  }[]
}

export interface CustomsPushResult {
  segment_id: string
  channel: string
  success: boolean
  message: string
  delivered_at: string | null
  compliance_checked: boolean
}

export interface CustomsROISegment {
  channel: string
  deliverable_buyers: number
  spend: number
  revenue: number
  roas: number
}

export interface CustomsROIPrediction {
  spend: number
  predicted_revenue: number
  predicted_roas: number
  predicted_profit: number
  confidence: number
  slope: number
  fit_r_squared: number
}

export interface CustomsROI {
  segments: CustomsROISegment[]
  blended_roas: number
  total_spend: number
  total_revenue: number
  ranking: { platform: string; roas: number; spend: number; revenue: number; trend_30d: number }[]
  roi_prediction: CustomsROIPrediction | null
}

export async function getCampaignSegments(): Promise<CustomsSegment[]> {
  const { data } = await client.get<CustomsSegment[]>('/api/customs-campaign/segments')
  return data
}

export async function getCampaignOverview(): Promise<CustomsOverview> {
  const { data } = await client.get<CustomsOverview>('/api/customs-campaign/overview')
  return data
}

export async function generateCampaignContent(payload: {
  segment_id: string
  brand: string
  brand_id?: string | null
  target_langs?: string[] | null
}): Promise<CustomsContent> {
  const { data } = await client.post<CustomsContent>('/api/customs-campaign/content', payload)
  return data
}

export async function pushCampaign(payload: {
  segment_id: string
  channel: string
  address: string
  brand?: string
  email?: string | null
  consent?: boolean | null
  unsubscribe_url?: string | null
  subject?: string | null
}): Promise<CustomsPushResult> {
  const { data } = await client.post<CustomsPushResult>('/api/customs-campaign/push', payload)
  return data
}

export async function attributeCampaignROI(payload: {
  total_budget?: number | null
  cost_per_contact?: number
  conversion_rate?: number
  deal_value?: number
}): Promise<CustomsROI> {
  const { data } = await client.post<CustomsROI>('/api/customs-campaign/roi', payload)
  return data
}
