import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, type MiningStage } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ThemeSwitch } from '@/components/theme-switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Play, Square, Terminal, Wifi, WifiOff, Trash2, Activity, Settings2, TrendingUp, ArrowRight,
} from 'lucide-react'

// ─── SSE 日志面板 ─────────────────────────────────────────────

function LogPanel({ kind }: { kind: 'digging' | 'check' }) {
  const [logs, setLogs] = useState<string[]>([])
  const [connected, setConnected] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)
  const retryDelayRef = useRef(5000)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const MAX_LOGS = 800

  const logColor = useCallback((line: string) => {
    if (/error|Error|失败|FATAL/i.test(line)) return 'text-red-400'
    if (/Limited|SIMULATION_LIMIT/i.test(line)) return 'text-orange-400'
    if (/PASS|successfully|成功|GREEN/i.test(line)) return 'text-green-400'
    if (/REJECT|DEAD|xin_plus.*0\.[7-9]|corr.*0\.[7-9]/i.test(line)) return 'text-red-400'
    if (/OPTIMIZE|YELLOW/i.test(line)) return 'text-yellow-400'
    if (/2step|order2/i.test(line)) return 'text-purple-400'
    if (/1step|order1/i.test(line)) return 'text-blue-400'
    if (/3step|order3/i.test(line)) return 'text-orange-300'
    if (/4step|order4/i.test(line)) return 'text-pink-400'
    if (/5step|order5/i.test(line)) return 'text-emerald-400'
    if (/Simulating|预检|quality/i.test(line)) return 'text-sky-400'
    if (/DSI|dsi/i.test(line)) return 'text-violet-400'
    return 'text-gray-300'
  }, [])

  const connect = useCallback(() => {
    if (esRef.current) esRef.current.close()
    const es = new EventSource(`/api/control/logs/${kind}`)
    esRef.current = es
    es.onopen = () => { setConnected(true); retryDelayRef.current = 5000 }
    es.onerror = () => {
      setConnected(false)
      const delay = retryDelayRef.current
      retryDelayRef.current = Math.min(delay * 2, 30_000)
      retryTimerRef.current = setTimeout(connect, delay)
    }
    es.onmessage = (e) => {
      setLogs((prev) => {
        const next = [...prev, e.data]
        return next.length > MAX_LOGS ? next.slice(-MAX_LOGS) : next
      })
    }
  }, [kind])

  useEffect(() => {
    connect()
    return () => {
      esRef.current?.close()
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
    }
  }, [connect])

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const title = kind === 'digging' ? 'Digging 日志' : 'Check 日志'
  const icon = kind === 'digging' ? '⛏' : '✅'

  return (
    <Card className='flex flex-col'>
      <CardHeader className='flex flex-row items-center justify-between pb-2 shrink-0'>
        <CardTitle className='flex items-center gap-2 text-sm'>
          <Terminal className='h-4 w-4' />
          {icon} {title}
          <span className='text-xs font-normal text-muted-foreground'>({logs.length} 行)</span>
        </CardTitle>
        <div className='flex items-center gap-2'>
          {connected
            ? <span className='flex items-center gap-1 text-xs text-green-500'><Wifi className='h-3.5 w-3.5' />LIVE</span>
            : <span className='flex items-center gap-1 text-xs text-red-500'><WifiOff className='h-3.5 w-3.5' />重连中</span>
          }
          <div className='flex items-center gap-1'>
            <Switch checked={autoScroll} onCheckedChange={setAutoScroll} className='scale-75' />
            <span className='text-xs text-muted-foreground'>滚动</span>
          </div>
          <Button variant='ghost' size='sm' className='h-7 px-2' onClick={() => setLogs([])}>
            <Trash2 className='h-3.5 w-3.5' />
          </Button>
        </div>
      </CardHeader>
      <CardContent className='p-0'>
        <div
          ref={scrollRef}
          className='h-80 overflow-y-auto font-mono text-xs bg-black/90 rounded-b-lg px-3 py-2 space-y-0.5'
          onScroll={(e) => {
            const el = e.currentTarget
            setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 30)
          }}
        >
          {logs.length === 0
            ? <p className='text-gray-600 text-center py-8'>等待日志输出…</p>
            : logs.map((line, i) => (
              <div key={i} className={`break-all leading-relaxed ${logColor(line)}`}>{line}</div>
            ))
          }
        </div>
      </CardContent>
    </Card>
  )
}

// ─── 阶段卡片 ─────────────────────────────────────────────────

const STAGE_ACCENT: Record<string, string> = {
  order1: 'border-blue-500/40 bg-blue-950/10',
  order2_group: 'border-purple-500/40 bg-purple-950/10',
  order3_decay: 'border-orange-500/40 bg-orange-950/10',
  order4_variant: 'border-pink-500/40 bg-pink-950/10',
  order5_prune: 'border-emerald-500/40 bg-emerald-950/10',
  check: 'border-green-500/40 bg-green-950/10',
}

const STAGE_BTN: Record<string, string> = {
  order1: 'bg-blue-600 hover:bg-blue-500',
  order2_group: 'bg-purple-600 hover:bg-purple-500',
  order3_decay: 'bg-orange-600 hover:bg-orange-500',
  order4_variant: 'bg-pink-600 hover:bg-pink-500',
  order5_prune: 'bg-emerald-700 hover:bg-emerald-600',
  check: 'bg-green-600 hover:bg-green-500',
}

const STAGE_BADGE_COLOR: Record<string, string> = {
  order1: 'border-blue-500 text-blue-400',
  order2_group: 'border-purple-500 text-purple-400',
  order3_decay: 'border-orange-500 text-orange-400',
  order4_variant: 'border-pink-500 text-pink-400',
  order5_prune: 'border-emerald-500 text-emerald-400',
  check: 'border-green-500 text-green-400',
}

function StageCard({
  stage, running, pid, simulated, candidateCount, candidateLabel = '晋级候选', loading, onStart, onStop,
}: {
  stage: MiningStage
  running: boolean
  pid: number | null
  simulated: number
  candidateCount?: number
  candidateLabel?: string
  loading: boolean
  onStart: () => void
  onStop: () => void
}) {
  const accentClass = running ? (STAGE_ACCENT[stage.id] ?? 'border-primary/40 bg-primary/5') : ''
  const btnClass = STAGE_BTN[stage.id] ?? 'bg-primary hover:bg-primary/90'
  const badgeClass = STAGE_BADGE_COLOR[stage.id] ?? 'border-border text-muted-foreground'

  return (
    <div className={`rounded-lg border p-4 transition-all space-y-2.5 ${running ? accentClass : 'border-border'}`}>
      {/* 顶部：ID badge + 运行状态 */}
      <div className='flex items-center justify-between'>
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold tracking-wider font-mono ${badgeClass}`}>
          {stage.id.toUpperCase()}
        </span>
        <div className='flex items-center gap-1.5'>
          {running && <span className='h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse' />}
          <span className={`text-[11px] font-semibold ${running ? 'text-green-500' : 'text-muted-foreground'}`}>
            {running ? '运行中' : '已停止'}
          </span>
        </div>
      </div>

      {/* 阶段名称和描述 */}
      <div>
        <p className='text-sm font-semibold'>{stage.label}</p>
        <p className='text-xs text-muted-foreground leading-relaxed'>{stage.description}</p>
      </div>

      {/* 输出 tag */}
      {stage.output_tag && (
        <p className='text-[10px] font-mono text-muted-foreground bg-muted/60 rounded px-1.5 py-0.5 truncate'>
          → {stage.output_tag}
        </p>
      )}

      {/* 统计信息行 */}
      <div className='flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground font-mono'>
        {simulated > 0 && <span>已模拟 <span className='text-foreground font-semibold'>{simulated.toLocaleString()}</span></span>}
        {candidateCount !== undefined && (
          <span className='flex items-center gap-0.5'>
            <ArrowRight className='h-2.5 w-2.5' />
            {candidateLabel} <span className='text-foreground font-semibold'>{candidateCount.toLocaleString()}</span>
          </span>
        )}
        {running && pid && <span>PID <span className='text-foreground'>{pid}</span></span>}
      </div>

      {/* 启停按钮 */}
      <Button
        className={`w-full text-xs text-white h-8 ${running ? 'bg-red-700 hover:bg-red-600' : btnClass}`}
        size='sm'
        disabled={loading}
        onClick={running ? onStop : onStart}
      >
        {running
          ? <><Square className='mr-1.5 h-3.5 w-3.5' />停止</>
          : <><Play className='mr-1.5 h-3.5 w-3.5' />启动</>}
      </Button>
    </div>
  )
}

// ─── 主页面 ───────────────────────────────────────────────────

export function ControlCenter() {
  const queryClient = useQueryClient()
  const [btnLoading, setBtnLoading] = useState<Record<string, boolean>>({})
  const [checkMode, setCheckMode] = useState('OFFICIAL')
  const [showConfig, setShowConfig] = useState(false)

  const { data: stagesData } = useQuery({ queryKey: ['stages'], queryFn: api.getStages, staleTime: 60_000 })
  const { data: controlStatus } = useQuery({ queryKey: ['control-status'], queryFn: api.getControlStatus, refetchInterval: 4_000 })
  const { data: pendingData } = useQuery({ queryKey: ['pending'], queryFn: api.getPendingCounts, refetchInterval: 30_000 })
  const { data: promotionData } = useQuery({ queryKey: ['promotion'], queryFn: api.getPromotion, staleTime: 120_000 })
  const { data: order5Queue } = useQuery({ queryKey: ['order5-queue'], queryFn: api.getOrder5Queue, refetchInterval: 60_000, staleTime: 30_000 })
  const { data: experiments } = useQuery({ queryKey: ['experiments'], queryFn: api.getExperiments, staleTime: 10_000 })
  const { data: diggingConfig } = useQuery({ queryKey: ['digging-config'], queryFn: api.getDiggingConfig, staleTime: 30_000 })
  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: api.getStats, refetchInterval: 20_000 })
  const { data: platformOverview } = useQuery({
    queryKey: ['platform-overview-control'],
    queryFn: api.getPlatformOverview,
    retry: 1,
    staleTime: 60_000,
    refetchInterval: 90_000,
  })

  useEffect(() => {
    api.getCheckMode().then((r) => setCheckMode(r.mode)).catch(() => {})
  }, [])

  const startMutation = useMutation({
    mutationFn: (id: string) => api.startScript(id),
    onSuccess: (_, id) => { queryClient.invalidateQueries({ queryKey: ['control-status'] }); setBtnLoading((p) => ({ ...p, [id]: false })) },
    onError: (err: Error, id) => { toast.error(`启动失败: ${err.message}`); setBtnLoading((p) => ({ ...p, [id]: false })) },
  })

  const stopMutation = useMutation({
    mutationFn: (id: string) => api.stopScript(id),
    onSuccess: (_, id) => { queryClient.invalidateQueries({ queryKey: ['control-status'] }); setBtnLoading((p) => ({ ...p, [id]: false })) },
    onError: (err: Error, id) => { toast.error(`停止失败: ${err.message}`); setBtnLoading((p) => ({ ...p, [id]: false })) },
  })

  function handleStart(id: string) { setBtnLoading((p) => ({ ...p, [id]: true })); startMutation.mutate(id) }
  function handleStop(id: string) { setBtnLoading((p) => ({ ...p, [id]: true })); stopMutation.mutate(id) }

  async function handleCheckMode(mode: string) {
    setCheckMode(mode)
    try {
      await api.setCheckMode(mode)
      toast.success(`Check 模式已切换为 ${mode}`)
    } catch (e: any) {
      toast.error(`设置失败: ${e.message}`)
    }
  }

  const stages = stagesData?.stages ?? []
  const diggingStages = stages.filter((s) => s.mutex_group === 'digging')
  const checkStage = stages.find((s) => s.id === 'check')

  const getStatus = (id: string) =>
    controlStatus?.[id] ?? { running: false, pid: null, enabled: true, reserved: false }

  // 候选流转 key mapping：Order5 是本地复核队列，不再叫“晋级候选”
  const pd = promotionData
  const candidateInfoMap: Record<string, { count: number; label: string }> = {
    order1: { count: pd?.['order1_to_order2']?.count ?? 0, label: '晋级候选' },
    order2_group: { count: pd?.['order2_to_order3']?.count ?? 0, label: '晋级候选' },
    order3_decay: { count: pd?.['order3_to_order4']?.count ?? 0, label: '晋级候选' },
    order4_variant: { count: pd?.['order4_to_order5']?.count ?? 0, label: '剪枝输入' },
    order5_prune: { count: order5Queue?.kept_total ?? 0, label: '复核队列' },
  }

  const flowStats = [
    { key: 'order1_to_order2', label: 'Order1 → Order2', stat: pd?.['order1_to_order2'], source: 'brain' },
    { key: 'order2_to_order3', label: 'Order2 → Order3', stat: pd?.['order2_to_order3'], source: 'brain' },
    { key: 'order3_to_order4', label: 'Order3 → Order4', stat: pd?.['order3_to_order4'], source: 'brain' },
    { key: 'order4_to_order5', label: 'Order4 → Order5 剪枝输入', stat: pd?.['order4_to_order5'], source: 'brain' },
    {
      key: 'order5_review_queue',
      label: 'Order5 复核队列',
      stat: { count: order5Queue?.kept_total ?? 0, threshold: undefined, error: undefined },
      source: 'local',
      suffix: order5Queue ? `总 ${order5Queue.total} / 剪枝 ${order5Queue.pruned_total}${order5Queue.no_pnl_total ? ` / 无PnL ${order5Queue.no_pnl_total}` : ''}` : undefined,
    },
  ]

  // 全局统计
  const anyRunning = Object.values(controlStatus ?? {}).some((s) => s.running)
  const runningId = Object.entries(controlStatus ?? {}).find(([, v]) => v.running)?.[0]

  return (
    <>
      <Header>
        <div className='ml-auto flex items-center gap-3'>
          {/* 全局简要统计 */}
          {stats && (
            <div className='hidden md:flex items-center gap-4 text-xs text-muted-foreground border rounded-md px-3 py-1.5'>
              <span>今日 <span className='text-foreground font-semibold'>{stats.today_ok}</span> 成功</span>
              <span>可提交 <span className='text-foreground font-semibold text-green-500'>{stats.submittable_count}</span></span>
              <span>成功率 <span className='text-foreground font-semibold'>{(stats.today_success_rate * 100).toFixed(1)}%</span></span>
            </div>
          )}
          <div className='flex items-center gap-1.5 text-sm'>
            <span className={`h-2 w-2 rounded-full ${anyRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
            <span className='text-muted-foreground text-xs'>{anyRunning ? (runningId ? `${runningId} 运行中` : '运行中') : '空闲'}</span>
          </div>
          <ThemeSwitch />
        </div>
      </Header>

      <Main>
        <div className='mb-5'>
          <h1 className='text-2xl font-bold tracking-tight'>脚本控制</h1>
          <p className='text-sm text-muted-foreground'>各阶段挖掘启停 · 实时日志 · 本地与平台真实数据</p>
        </div>

        {/* 总览数据条：本地 + 平台真实数据 */}
        <div className='mb-4 grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6'>
          <div className='rounded-lg border bg-card px-3 py-2'>
            <p className='text-[10px] uppercase tracking-wider text-muted-foreground'>当前运行</p>
            <p className='mt-0.5 text-sm font-semibold flex items-center gap-1.5'>
              <span className={`h-2 w-2 rounded-full ${anyRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
              {anyRunning ? (runningId ?? '运行中') : '空闲'}
            </p>
          </div>
          <div className='rounded-lg border bg-card px-3 py-2'>
            <p className='text-[10px] uppercase tracking-wider text-muted-foreground'>Check 模式</p>
            <p className='mt-0.5 text-sm font-semibold font-mono'>{checkMode}</p>
          </div>
          <div className='rounded-lg border bg-card px-3 py-2'>
            <p className='text-[10px] uppercase tracking-wider text-muted-foreground'>今日模拟</p>
            <p className='mt-0.5 text-sm font-semibold'>{stats?.today_simulated ?? '—'} <span className='text-xs font-normal text-muted-foreground'>成功 {stats?.today_ok ?? 0}</span></p>
          </div>
          <div className='rounded-lg border bg-card px-3 py-2'>
            <p className='text-[10px] uppercase tracking-wider text-muted-foreground'>本地可提交</p>
            <p className='mt-0.5 text-sm font-semibold text-green-500'>{stats?.submittable_count ?? '—'}</p>
          </div>
          <div className='rounded-lg border bg-card px-3 py-2'>
            <p className='text-[10px] uppercase tracking-wider text-muted-foreground'>平台 OS / IS</p>
            <p className='mt-0.5 text-sm font-semibold font-mono'>
              {platformOverview
                ? `${platformOverview.alphas_os_count < 0 ? '—' : platformOverview.alphas_os_count} / ${platformOverview.alphas_is_count < 0 ? '—' : platformOverview.alphas_is_count}${platformOverview.is_capped ? '+' : ''}`
                : '— / —'}
            </p>
          </div>
          <div className='rounded-lg border bg-card px-3 py-2'>
            <p className='text-[10px] uppercase tracking-wider text-muted-foreground'>平台未提交</p>
            <p className='mt-0.5 text-sm font-semibold font-mono'>
              {platformOverview
                ? (platformOverview.unsubmitted_count < 0 ? '—' : `${platformOverview.unsubmitted_count}${platformOverview.unsubmitted_capped ? '+' : ''}`)
                : '—'}
            </p>
          </div>
        </div>

        {/* Tag 映射 + 晋级概览 */}
        <Card className='mb-4'>
          <CardContent className='pt-4 pb-4'>
            <div className='flex flex-wrap items-start gap-6'>
              <div className='min-w-0 flex-1'>
                <div className='flex items-center gap-2 flex-wrap'>
                  <span className='text-xs text-muted-foreground'>当前 Tag 方案:</span>
                  <Badge variant='secondary' className='font-mono text-xs'>{experiments?.active || 'baseline'}</Badge>
                  <span className='text-xs text-muted-foreground'>实验切换已废弃，按设置页参数动态生成 tag</span>
                </div>
                <div className='mt-2 grid gap-1 text-[11px] font-mono text-muted-foreground sm:grid-cols-2 lg:grid-cols-3'>
                  {Object.entries((experiments?.experiments?.[experiments?.active || 'baseline'] ?? {}) as Record<string, string>)
                    .filter(([k]) => k.endsWith('_tag'))
                    .map(([k, v]) => (
                      <div key={k} className='rounded bg-muted/60 px-2 py-1'>
                        <span className='text-muted-foreground'>{k}: </span>
                        <span className='text-foreground'>{v || '—'}</span>
                      </div>
                    ))}
                </div>
                <p className='mt-1.5 text-xs text-muted-foreground'>Order 1→5 共用同一套 baseline 阶段 tag；如需改数据集/region/delay，请到设置页修改参数。</p>
              </div>

              {/* 候选流转概览 */}
              {(promotionData || order5Queue) && (
                <div className='space-y-1.5 text-xs shrink-0'>
                  <p className='text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1'>
                    <TrendingUp className='h-3.5 w-3.5' />候选流转（平台查询 / 本地队列）
                  </p>
                  {flowStats.map((row) => (
                    <div key={row.key} className='flex items-center gap-2'>
                      <span className='text-muted-foreground w-40 truncate'>{row.label}</span>
                      <Badge variant={(row.stat?.count ?? 0) > 0 ? 'default' : 'outline'} className='text-[10px]'>
                        {row.stat?.error ? '查询失败' : `${row.stat?.count ?? 0} 个`}
                      </Badge>
                      {row.stat?.threshold && (
                        <span className='text-muted-foreground'>
                          (S≥{row.stat.threshold.sharpe} / F≥{row.stat.threshold.fitness})
                        </span>
                      )}
                      {row.suffix && <span className='text-muted-foreground'>({row.suffix})</span>}
                    </div>
                  ))}
                  <p className='text-[10px] text-muted-foreground'>Order1-4 为 Brain 平台查询；Order5 为本地复核队列。失败不影响脚本启停。</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Digging 阶段组 */}
        <Card className='mb-4'>
          <CardHeader className='pb-2'>
            <CardTitle className='flex items-center gap-2 text-base'>
              <Activity className='h-4 w-4' />
              Digging 阶段
              <span className='text-xs font-normal text-muted-foreground'>互斥，同时只能运行一个</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5'>
              {diggingStages.map((stage) => {
                const st = getStatus(stage.id)
                return (
                  <StageCard
                    key={stage.id}
                    stage={stage}
                    running={st.running}
                    pid={st.pid}
                    simulated={pendingData?.[stage.id]?.simulated ?? 0}
                    candidateCount={candidateInfoMap[stage.id]?.count}
                    candidateLabel={candidateInfoMap[stage.id]?.label}
                    loading={btnLoading[stage.id] ?? false}
                    onStart={() => handleStart(stage.id)}
                    onStop={() => handleStop(stage.id)}
                  />
                )
              })}
            </div>
          </CardContent>
        </Card>

        {/* Check + 配置行 */}
        <div className='mb-4 grid gap-4 md:grid-cols-2'>
          {/* Check 阶段 */}
          {checkStage && (
            <Card>
              <CardHeader className='pb-2'>
                <CardTitle className='text-sm flex items-center gap-2'>
                  ✅ Check
                  <span className='text-xs font-normal text-muted-foreground'>可与 Digging 同时运行</span>
                </CardTitle>
              </CardHeader>
              <CardContent className='space-y-3'>
                <StageCard
                  stage={checkStage}
                  running={getStatus('check').running}
                  pid={getStatus('check').pid}
                  simulated={0}
                  loading={btnLoading['check'] ?? false}
                  onStart={() => handleStart('check')}
                  onStop={() => handleStop('check')}
                />
                <div className='space-y-2 pt-1'>
                  <p className='text-xs font-semibold text-muted-foreground uppercase tracking-wider'>提交前相关性检查</p>
                  <p className='text-xs text-muted-foreground'>独立于挖掘质量门控，过滤高自相关因子</p>
                  <div className='flex gap-2'>
                    {(['FAST', 'OFFICIAL'] as const).map((m) => (
                      <button
                        key={m}
                        className={`rounded border px-3 py-1 text-xs font-bold font-mono transition-colors
                          ${checkMode === m
                            ? 'border-green-500 bg-green-500/15 text-green-400'
                            : 'border-border text-muted-foreground hover:border-green-500/50 hover:text-green-400'}`}
                        onClick={() => handleCheckMode(m)}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                  <p className='text-xs text-muted-foreground'>
                    {checkMode === 'FAST'
                      ? '仅 xin_plus 近似粗筛，不调官方接口，速度最快'
                      : 'xin_plus → 本地 PnL 剪枝 → 官方 self-corr（完整流程）'}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 挖掘配置（折叠面板） */}
          <Card>
            <CardHeader
              className='cursor-pointer pb-2'
              onClick={() => setShowConfig(!showConfig)}
            >
              <CardTitle className='flex items-center justify-between text-sm'>
                <div className='flex items-center gap-2'>
                  <Settings2 className='h-4 w-4' />
                  当前挖掘配置
                </div>
                <span className='text-xs font-normal text-muted-foreground'>{showConfig ? '收起' : '展开'}</span>
              </CardTitle>
            </CardHeader>
            {diggingConfig && (
              <CardContent>
                {showConfig ? (
                  <div className='grid grid-cols-2 gap-2 text-sm'>
                    {Object.entries(diggingConfig).map(([k, v]) => (
                      <div key={k}>
                        <p className='text-[10px] text-muted-foreground uppercase tracking-wider'>{k}</p>
                        <p className='font-mono text-xs'>{String(v)}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className='flex flex-wrap gap-2'>
                    {['dataset_id', 'region', 'universe', 'delay', 'decay', 'neutralization'].map((k) => (
                      <div key={k} className='flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs font-mono'>
                        <span className='text-muted-foreground'>{k}:</span>
                        <span>{String(diggingConfig[k] ?? '—')}</span>
                      </div>
                    ))}
                  </div>
                )}
                <p className='mt-2 text-[10px] text-muted-foreground'>在设置页可动态修改，或直接编辑 records/digging_config.json</p>
              </CardContent>
            )}
          </Card>
        </div>

        {/* 日志双栏 */}
        <div className='grid gap-4 lg:grid-cols-2'>
          <LogPanel kind='digging' />
          <LogPanel kind='check' />
        </div>
      </Main>
    </>
  )
}
