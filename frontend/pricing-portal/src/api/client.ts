import axios from 'axios'

const client = axios.create({
  baseURL: '/fde-api',
  timeout: 60000,
})

export interface PricingOverview {
  total_products: number
  avg_margin_pct: number
  total_est_revenue: number
  opportunity_count: number
  category_distribution: { category: string; count: number }[]
  top_opportunities: {
    product_id: string
    name: string
    category: string
    current_price: number
    recommended_price: number
    expected_delta_profit_pct: number
    expected_delta_revenue_pct: number
    expected_delta_volume_pct: number
  }[]
}

export interface ProductSummary {
  product_id: string
  name: string
  category: string
  cost: number
  current_price: number
  margin_pct: number
}

export interface DemandForecast {
  product_id: string
  history: { t: number; actual: number; fitted: number }[]
  forecast: { t: number; value: number; lower: number; upper: number }[]
  seasonal_period: number
  trend_slope: number
  residual_std: number
}

export interface ElasticityResult {
  product_id: string
  elasticity: number
  r_squared: number
  interpretation: string
  is_elastic: boolean
}

export interface CompetitorSnapshot {
  product_id: string
  own_price: number
  competitors: { competitor: string; price: number }[]
  avg_competitor: number
  min_competitor: number
  max_competitor: number
  position: string
}

export interface ProductDetail {
  product: { product_id: string; name: string; category: string; cost: number; current_price: number }
  sales_history: { date: string; price: number; quantity: number }[]
  competitors: CompetitorSnapshot
}

export interface OptimizationResult {
  product_id: string
  current_price: number
  recommended_price: number
  expected_delta_revenue_pct: number
  expected_delta_profit_pct: number
  expected_delta_volume_pct: number
  strategy: string
  rationale: string
  confidence: number
  elasticity: ElasticityResult
  competitors: CompetitorSnapshot
  rl_log?: { episodes: number[]; prices: number[]; best_price: number; best_profit: number; final_policy_mean: number; iterations: number }
}

export interface SimulatorResult {
  product_id: string
  current_price: number
  new_price: number
  current_volume: number
  projected_volume: number
  current_revenue: number
  projected_revenue: number
  current_profit: number
  projected_profit: number
  delta_revenue_pct: number
  delta_profit_pct: number
  delta_volume_pct: number
  elasticity_used: number
}

export interface StrategyPreset {
  key: string
  name: string
  desc: string
}

export async function getOverview(): Promise<PricingOverview> {
  const { data } = await client.get<PricingOverview>('/api/pricing/overview')
  return data
}

export async function getProducts(): Promise<ProductSummary[]> {
  const { data } = await client.get<ProductSummary[]>('/api/pricing/products')
  return data
}

export async function getProductDetail(productId: string): Promise<ProductDetail> {
  const { data } = await client.get<ProductDetail>(`/api/pricing/products/${productId}`)
  return data
}

export async function forecast(productId: string, periods = 14): Promise<DemandForecast> {
  const { data } = await client.post<DemandForecast>(`/api/pricing/forecast/${productId}?periods=${periods}`)
  return data
}

export async function getElasticity(productId: string): Promise<ElasticityResult> {
  const { data } = await client.get<ElasticityResult>(`/api/pricing/elasticity/${productId}`)
  return data
}

export async function getCompetitors(productId: string): Promise<CompetitorSnapshot> {
  const { data } = await client.get<CompetitorSnapshot>(`/api/pricing/competitors/${productId}`)
  return data
}

export async function optimize(productId: string, strategy = 'rl_optimal'): Promise<OptimizationResult> {
  const { data } = await client.post<OptimizationResult>(`/api/pricing/optimize/${productId}?strategy=${strategy}`)
  return data
}

export async function simulate(payload: { product_id: string; new_price: number }): Promise<SimulatorResult> {
  const { data } = await client.post<SimulatorResult>('/api/pricing/simulate', payload)
  return data
}

export async function getStrategies(): Promise<StrategyPreset[]> {
  const { data } = await client.get<StrategyPreset[]>('/api/pricing/strategies')
  return data
}
