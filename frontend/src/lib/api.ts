/**
 * Alpha Mining Dashboard — API 客户端
 * 统一对接 alpha 后端 FastAPI 接口
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly path: string,
    message: string
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 45_000)
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    })
    if (!res.ok) {
      const raw = await res.text().catch(() => res.statusText)
      let detail = raw || res.statusText
      try {
        const parsed = JSON.parse(raw)
        detail = parsed.detail || parsed.message || raw
      } catch {
        // keep raw text
      }
      throw new ApiError(res.status, path, `API ${path} 失败 (${res.status})：${detail}`)
    }
    if (res.status === 204) return undefined as T
    return res.json() as Promise<T>
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError(408, path, `API ${path} 请求超时：后端或 Brain 平台响应超过 45 秒，请稍后重试。`)
    }
    const message = err instanceof Error ? err.message : String(err)
    throw new ApiError(0, path, `无法连接后端 API ${path}：${message}`)
  } finally {
    clearTimeout(timeoutId)
  }
}

// ─── 类型定义 ─────────────────────────────────────────────────

export interface AlphaItem {
  id: string
  code: string
  region: string
  universe: string
  delay: number
  decay: number
  sharpe: number | null
  fitness: number | null
  turnover: number | null
  returns: number | null
  margin: number | null
  longCount: number | null
  shortCount: number | null
  dateCreated: string | null
  color: string | null
  tags: string | null
  self_corr: number | null
  prod_corr: number | null
  quality_status: string | null
  signal_light: string | null
  quality_tier: string | null
  quality_reasons: string | null
  review_status: string | null
  review_note: string | null
  check_time: string | null
  official_check_status: string | null
  fallback_used: boolean | null
  review_priority: number | null
  dsi_signal: string | null
}

export interface AlphaListResponse {
  alphas: AlphaItem[]
  total: number
}

export interface StatsData {
  today_simulated: number
  today_ok: number
  today_success_rate: number
  avg_duration_s: number
  step1_total: number
  step2_total: number
  step3_total: number
  total_simulated: number
  status_counts: Record<string, number>
  submittable_count: number
  hourly_counts: number[]
  events_today: number
  event_counts: Record<string, number>
  phase_counts: Record<string, number>
  skip_counts: Record<string, number>
  error_count: number
  recent_events: Array<{
    ts: string
    phase: string
    event: string
    detail: string
    counts: Record<string, number>
    extra?: Record<string, unknown>
  }>
  // 质量统计（依赖 simulate_single 写入 quality_status）
  today_pass?: number
  today_optimize?: number
  today_reject?: number
  today_quality_unknown?: number
  today_green?: number
  today_yellow?: number
  today_red?: number
  today_dead?: number
}

export interface StatusData {
  phase: string
  detail: string
  updated_at: string
  last_event: Record<string, unknown> | null
  control_status_api: string
  server_uptime_s: number
}

export interface MiningStage {
  id: string
  label: string
  description: string
  script: string | null
  input_tag_key: string | null
  output_tag_key: string | null
  input_tag: string | null
  output_tag: string | null
  mutex_group: string | null
  enabled: boolean
  log_file: string
  reserved: boolean
}

export interface ScriptStatus {
  running: boolean
  pid: number | null
  enabled: boolean
  reserved: boolean
  script?: string
  log_file?: string
}

export interface PendingCount {
  simulated: number
  tag: string
}

export interface ExperimentsResponse {
  active: string
  experiments: Record<string, {
    description?: string
    step1_tag?: string
    step2_tag?: string
    step3_tag?: string
    order4_tag?: string
    order5_tag?: string
  }>
  experiment_switch_deprecated?: boolean
  message?: string
}

export interface FunnelData {
  total: number
  success: number
  duplicated: number
  passed_check: number
  by_step: Record<string, { total: number; success: number }>
}

export interface DistributionData {
  total: number
  sharpe: Record<string, number>
  fitness: Record<string, number>
}

export interface TimelineData {
  dates: string[]
  series: Record<string, number[]>
}

export interface ScatterData {
  points: Array<{
    id: string
    sharpe: number
    fitness: number
    turnover: number | null
    step: string
    code: string
  }>
  total: number
}

export interface PlatformOverview {
  user_id: string | null
  full_name: string | null
  genius_level: string | null
  alphas_os_count: number
  alphas_is_count: number
  is_capped: boolean
  unsubmitted_count: number
  unsubmitted_capped: boolean
  os_capped: boolean
  total_alphas: number
  stage_counts: Record<string, number>
  fetched_at: string
}

export interface PlatformAlphaItem {
  id: string
  code: string
  dateCreated: string | null
  stage: string | null
  status: string | null
  color: string | null
  tags: string[]
  region: string | null
  universe: string | null
  decay: number | null
  sharpe: number | null
  fitness: number | null
  returns: number | null
  turnover: number | null
  margin: number | null
  longCount: number | null
  shortCount: number | null
}

export interface PlatformAlphasResponse {
  total: number
  page: number
  limit: number
  stage: string
  items: PlatformAlphaItem[]
}

export interface PromotionStat {
  from_tag?: string
  threshold?: Record<string, number>
  count: number
  source?: 'brain' | 'local'
  error?: string
}

export interface Order5QueueResponse {
  items: AlphaItem[]
  total: number
  kept_total: number
  pruned_total: number
  no_pnl_total?: number
  message?: string
}

// ─── API ─────────────────────────────────────────────────────

export const api = {
  // 状态监控
  getStatus: () => request<StatusData>('/status'),
  getStats: () => request<StatsData>('/stats'),
  getSimulations: (params?: { page?: number; limit?: number; tag?: string; status?: string }) => {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)))
    return request<{ total: number; page: number; limit: number; items: unknown[] }>(`/simulations?${qs}`)
  },
  getLogs: (n?: number, kind?: string) => {
    const qs = new URLSearchParams()
    if (n) qs.set('n', String(n))
    if (kind) qs.set('kind', kind)
    return request<{ lines: string[] }>(`/logs?${qs}`)
  },

  // Alpha 因子
  getAlphas: () => request<AlphaListResponse>('/alphas'),
  getDistribution: (tag?: string) => {
    const qs = tag ? `?tag=${tag}` : ''
    return request<DistributionData>(`/alphas/distribution${qs}`)
  },
  getTimeline: (days?: number, tag?: string) => {
    const qs = new URLSearchParams()
    if (days) qs.set('days', String(days))
    if (tag) qs.set('tag', tag)
    return request<TimelineData>(`/alphas/timeline?${qs}`)
  },
  getFunnel: () => request<FunnelData>('/alphas/funnel'),
  getTopAlphas: (params?: { n?: number; sort?: string; tag?: string }) => {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)))
    return request<{ items: AlphaItem[]; total: number }>(`/alphas/top?${qs}`)
  },
  getScatter: (tag?: string) => {
    const qs = tag ? `?tag=${tag}` : ''
    return request<ScatterData>(`/alphas/scatter${qs}`)
  },

  // 脚本阶段控制
  getStages: () => request<{ stages: MiningStage[] }>('/control/stages'),
  getControlStatus: () => request<Record<string, ScriptStatus>>('/control/status'),
  getPendingCounts: () => request<Record<string, PendingCount>>('/control/pending'),
  startScript: (name: string) => request<{ status: string; stage: string; pid?: number }>(`/control/start/${name}`, { method: 'POST' }),
  stopScript: (name: string) => request<{ status: string; stage: string }>(`/control/stop/${name}`, { method: 'POST' }),
  getCheckMode: () => request<{ mode: string }>('/control/check-mode'),
  setCheckMode: (mode: string) => request<{ mode: string }>('/control/check-mode', { method: 'POST', body: JSON.stringify({ mode }) }),
  getDiggingConfig: () => request<Record<string, unknown>>('/control/digging-config'),
  setDiggingConfig: (config: Record<string, unknown>) => request<{ success: boolean; config: Record<string, unknown> }>('/control/digging-config', { method: 'POST', body: JSON.stringify(config) }),

  // A/B 实验
  getExperiments: () => request<ExperimentsResponse>('/experiments'),
  switchExperiment: (name: string) => request<{ status: string; active: string }>('/experiments/switch', { method: 'POST', body: JSON.stringify({ name }) }),

  // 平台数据
  getPlatformOverview: () => request<PlatformOverview>('/platform/overview'),
  getPlatformAlphas: (params?: { stage?: string; page?: number; limit?: number; order?: string }) => {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)))
    return request<PlatformAlphasResponse>(`/platform/alphas?${qs}`)
  },

  // 人工提交 / 审核 / 官方检查
  submitAlpha: (alphaId: string) =>
    request<{ status: string; alpha_id: string; message: string }>(`/alphas/${alphaId}/submit`, { method: 'POST' }),
  updateReview: (alphaId: string, body: { review_status?: string; review_note?: string }) =>
    request<{ alpha_id: string; updated: Record<string, string> }>(`/alphas/${alphaId}/review`, { method: 'PATCH', body: JSON.stringify(body) }),
  officialCheck: (alphaId: string) =>
    request<{ alpha_id: string; checks: Array<{ name: string; result: string; value?: number; limit?: number }>; raw?: unknown }>(`/alphas/${alphaId}/official-check`),
  getOrder5Queue: () =>
    request<Order5QueueResponse>('/alphas/order5-queue'),

  // 晋级候选统计
  getPromotion: () =>
    request<Record<string, PromotionStat>>('/control/promotion').catch(() => ({} as Record<string, PromotionStat>)),

  // 统一配置
  getFullConfig: () => request<{
    credentials: { email: string; configured: boolean }
    digging: Record<string, unknown>
    check_mode: string
    tags: Record<string, string>
    active_experiment: string
  }>('/config'),

  patchConfig: (updates: Record<string, unknown>) =>
    request<{ status: string; updated: string[] }>('/config', { method: 'PATCH', body: JSON.stringify(updates) }),

  getCredentialStatus: () => request<{ configured: boolean; email: string }>('/config/credentials'),

  saveCredentials: (email: string, password: string) =>
    request<{ status: string; email: string }>('/config/credentials', { method: 'POST', body: JSON.stringify({ email, password }) }),

  testLogin: (email: string, password: string) =>
    request<{ status: string; message: string }>('/config/test-login', { method: 'POST', body: JSON.stringify({ email, password }) }),
}
