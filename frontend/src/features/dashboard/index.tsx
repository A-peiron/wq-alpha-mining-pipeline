import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ThemeSwitch } from '@/components/theme-switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line,
} from 'recharts'
import {
  FlaskConical, TrendingUp, CheckCircle, Zap, Clock, BarChart3, RefreshCw,
} from 'lucide-react'

const SIGNAL_COLORS: Record<string, string> = {
  GREEN: 'bg-green-500',
  YELLOW: 'bg-yellow-400',
  RED: 'bg-red-500',
  DEAD: 'bg-gray-500',
}

const SIGNAL_LABELS: Record<string, string> = {
  GREEN: '直接提交',
  YELLOW: '继续迭代',
  RED: '需优化',
  DEAD: '换方向',
}

const STEP_COLORS: Record<string, string> = {
  '1step': '#3b82f6',
  '2step': '#a855f7',
  '3step': '#f97316',
  unknown: '#64748b',
}

function StatCard({ title, value, sub, icon: Icon, accent }: {
  title: string; value: string | number; sub?: string; icon: React.ElementType; accent?: string
}) {
  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between pb-2'>
        <CardTitle className='text-sm font-medium text-muted-foreground'>{title}</CardTitle>
        <Icon className={`h-4 w-4 ${accent ?? 'text-muted-foreground'}`} />
      </CardHeader>
      <CardContent>
        <div className='text-2xl font-bold'>{value}</div>
        {sub && <p className='mt-1 text-xs text-muted-foreground'>{sub}</p>}
      </CardContent>
    </Card>
  )
}

function SignalDot({ signal }: { signal: string | null }) {
  const color = SIGNAL_COLORS[signal ?? ''] ?? 'bg-gray-300'
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
}

export function Dashboard() {
  const { data: stats, isLoading, refetch } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    refetchInterval: 15_000,
  })

  const { data: controlStatus } = useQuery({
    queryKey: ['control-status'],
    queryFn: api.getControlStatus,
    refetchInterval: 8_000,
  })

  const { data: funnel } = useQuery({
    queryKey: ['funnel'],
    queryFn: api.getFunnel,
    refetchInterval: 30_000,
  })

  const isRunning = controlStatus
    ? Object.values(controlStatus).some((s) => s.running)
    : false

  // 当前运行阶段名
  const runningStage = controlStatus
    ? Object.entries(controlStatus).find(([, v]) => v.running)?.[0] ?? null
    : null

  // 质量分布（优先用 stats 中的质量字段，回退到 events 近似）
  const hasQualityData = (stats?.today_pass ?? 0) + (stats?.today_optimize ?? 0) + (stats?.today_reject ?? 0) > 0
  const qualityItems = hasQualityData ? [
    { label: 'PASS', count: stats?.today_pass ?? 0, color: 'bg-green-500' },
    { label: 'OPTIMIZE', count: stats?.today_optimize ?? 0, color: 'bg-yellow-400' },
    { label: 'REJECT', count: stats?.today_reject ?? 0, color: 'bg-red-500' },
  ] : []

  const signalItems = hasQualityData ? [
    { label: 'GREEN', count: stats?.today_green ?? 0, color: 'bg-green-500' },
    { label: 'YELLOW', count: stats?.today_yellow ?? 0, color: 'bg-yellow-400' },
    { label: 'RED', count: stats?.today_red ?? 0, color: 'bg-red-500' },
    { label: 'DEAD', count: stats?.today_dead ?? 0, color: 'bg-gray-500' },
  ] : []

  const hourlyData = (stats?.hourly_counts ?? Array(24).fill(0)).map((v, i) => {
    const now = new Date()
    const h = new Date(now.getTime() - (23 - i) * 3600000).getHours()
    return { hour: `${String(h).padStart(2, '0')}:00`, count: v }
  })

  const byStepData = funnel
    ? Object.entries(funnel.by_step).map(([step, d]) => ({
        step,
        total: d.total,
        success: d.success,
        fill: STEP_COLORS[step] ?? STEP_COLORS.unknown,
      }))
    : []

  // 跳过原因分布
  const skipData = stats
    ? Object.entries(stats.skip_counts).map(([reason, count]) => ({ reason, count }))
    : []

  // 根据 events 中的 check 粗筛事件构建信号灯近似统计
  const recentCheckEvents = (stats?.recent_events ?? []).filter(
    (e) => e.event === 'submitable_found'
  )
  const signalCounts: Record<string, number> = { GREEN: 0, YELLOW: 0, RED: 0, DEAD: 0 }
  for (const e of recentCheckEvents) {
    const sig = (e as any).extra?.signal_light as string | undefined
    if (sig && sig in signalCounts) signalCounts[sig]++
  }
  const totalSignals = Object.values(signalCounts).reduce((a, b) => a + b, 0)

  return (
    <>
      <Header>
        <div className='ml-auto flex items-center gap-3'>
          <div className='flex items-center gap-1.5 text-sm'>
            <span className={`h-2 w-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
            <span className='text-muted-foreground'>{isRunning ? '运行中' : '已停止'}</span>
          </div>
          <Button variant='outline' size='sm' onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className='mr-1 h-3.5 w-3.5' />
            刷新
          </Button>
          <ThemeSwitch />
        </div>
      </Header>

      <Main>
        {/* 顶部状态条 */}
        <div className='mb-4 flex items-center gap-3 rounded-lg border bg-muted/40 px-4 py-2 text-sm'>
          <span className={`h-2 w-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
          <span className='font-medium'>{isRunning ? (runningStage ? `${runningStage} 运行中` : '运行中') : '已停止'}</span>
          {stats?.recent_events?.length ? (
            <span className='text-xs text-muted-foreground ml-2 truncate'>
              最近: {stats.recent_events[stats.recent_events.length - 1]?.detail || stats.recent_events[stats.recent_events.length - 1]?.event}
            </span>
          ) : null}
        </div>

        <div className='mb-6'>
          <h1 className='text-2xl font-bold tracking-tight'>挖掘看板</h1>
          <p className='text-sm text-muted-foreground'>WorldQuant BRAIN 因子挖掘系统实时状态</p>
        </div>

        {/* 核心指标卡片 */}
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
          <StatCard
            title='今日模拟'
            value={stats?.today_simulated ?? '—'}
            sub={`成功 ${stats?.today_ok ?? 0} · 成功率 ${stats ? (stats.today_success_rate * 100).toFixed(1) : 0}%`}
            icon={Zap}
            accent='text-blue-500'
          />
          <StatCard
            title='总模拟次数'
            value={stats?.total_simulated?.toLocaleString() ?? '—'}
            sub={`Step1 ${stats?.step1_total ?? 0} · Step2 ${stats?.step2_total ?? 0} · Step3 ${stats?.step3_total ?? 0}`}
            icon={BarChart3}
          />
          <StatCard
            title='可提交因子'
            value={stats?.submittable_count ?? '—'}
            sub='已通过本地 self-corr 检验'
            icon={CheckCircle}
            accent='text-green-500'
          />
          <StatCard
            title='平均耗时'
            value={stats?.avg_duration_s != null ? `${stats.avg_duration_s}s` : '—'}
            sub={`今日错误 ${stats?.error_count ?? 0} 次`}
            icon={Clock}
            accent='text-orange-500'
          />
        </div>

        <div className='mt-6 grid gap-4 lg:grid-cols-3'>
          {/* 24h 模拟趋势 */}
          <Card className='lg:col-span-2'>
            <CardHeader>
              <CardTitle className='flex items-center gap-2 text-base'>
                <TrendingUp className='h-4 w-4' />
                过去 24 小时模拟量
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width='100%' height={180}>
                <LineChart data={hourlyData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <XAxis dataKey='hour' tick={{ fontSize: 10 }} interval={3} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v: unknown) => [`${v} 次`, '模拟数量']} />
                  <Line type='monotone' dataKey='count' stroke='#22c55e' dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* DSI 信号灯近似分布 */}
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2 text-base'>
                <BarChart3 className='h-4 w-4' />
                Check 通过因子信号灯
              </CardTitle>
            </CardHeader>
            <CardContent className='space-y-3'>
              {(['GREEN', 'YELLOW', 'RED', 'DEAD'] as const).map((s) => {
                const count = signalCounts[s]
                const pct = totalSignals > 0 ? Math.round((count / totalSignals) * 100) : 0
                return (
                  <div key={s} className='flex items-center gap-3'>
                    <SignalDot signal={s} />
                    <div className='flex-1'>
                      <div className='flex justify-between text-sm'>
                        <span>{s}<span className='ml-1 text-xs text-muted-foreground'>{SIGNAL_LABELS[s]}</span></span>
                        <span className='font-medium'>{count}</span>
                      </div>
                      <div className='mt-1 h-1 w-full rounded-full bg-muted'>
                        <div className={`h-1 rounded-full ${SIGNAL_COLORS[s]}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </div>

        <div className='mt-4 grid gap-4 lg:grid-cols-2'>
          {/* 漏斗 by step */}
          {byStepData.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className='text-base'>各阶段模拟漏斗</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width='100%' height={180}>
                  <BarChart data={byStepData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <XAxis dataKey='step' tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey='total' name='总模拟' radius={[3, 3, 0, 0]}>
                      {byStepData.map((entry) => (
                        <Cell key={entry.step} fill={`${entry.fill}80`} stroke={entry.fill} strokeWidth={1} />
                      ))}
                    </Bar>
                    <Bar dataKey='success' name='成功' radius={[3, 3, 0, 0]}>
                      {byStepData.map((entry) => (
                        <Cell key={entry.step} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* 预检跳过原因分布 */}
          {skipData.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className='text-base'>预检跳过原因分布（今日）</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width='100%' height={180}>
                  <BarChart data={skipData} layout='vertical' margin={{ top: 4, right: 8, left: 80, bottom: 0 }}>
                    <XAxis type='number' tick={{ fontSize: 10 }} />
                    <YAxis type='category' dataKey='reason' tick={{ fontSize: 10 }} width={80} />
                    <Tooltip />
                    <Bar dataKey='count' fill='#64748b' radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>

        {/* 今日质量分布（依赖 simulate_single 质量标签写入后才有意义） */}
        {qualityItems.length > 0 && (
          <div className='mt-4 grid gap-4 lg:grid-cols-2'>
            <Card>
              <CardHeader><CardTitle className='text-base flex items-center gap-2'><BarChart3 className='h-4 w-4' />今日质量状态</CardTitle></CardHeader>
              <CardContent className='space-y-3'>
                {qualityItems.map(({ label, count, color }) => {
                  const total = qualityItems.reduce((a, b) => a + b.count, 0)
                  const pct = total > 0 ? Math.round((count / total) * 100) : 0
                  return (
                    <div key={label} className='flex items-center gap-3'>
                      <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
                      <div className='flex-1'>
                        <div className='flex justify-between text-sm mb-1'>
                          <span>{label}</span><span className='font-medium'>{count}</span>
                        </div>
                        <div className='h-1 w-full rounded-full bg-muted'>
                          <div className={`h-1 rounded-full ${color}`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className='text-base'>今日信号灯分布</CardTitle></CardHeader>
              <CardContent className='space-y-3'>
                {signalItems.map(({ label, count, color }) => {
                  const total = signalItems.reduce((a, b) => a + b.count, 0)
                  const pct = total > 0 ? Math.round((count / total) * 100) : 0
                  return (
                    <div key={label} className='flex items-center gap-3'>
                      <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
                      <div className='flex-1'>
                        <div className='flex justify-between text-sm mb-1'>
                          <span>{label}</span><span className='font-medium'>{count}</span>
                        </div>
                        <div className='h-1 w-full rounded-full bg-muted'>
                          <div className={`h-1 rounded-full ${color}`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          </div>
        )}

        {/* 最近事件 */}
        {(stats?.recent_events?.length ?? 0) > 0 && (
          <Card className='mt-4'>
            <CardHeader>
              <CardTitle className='flex items-center gap-2 text-base'>
                <FlaskConical className='h-4 w-4' />
                最近事件
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className='space-y-1.5 font-mono text-xs'>
                {(stats?.recent_events ?? []).slice(-10).reverse().map((e, i) => (
                  <div key={i} className='flex gap-3 text-muted-foreground'>
                    <span className='shrink-0 text-xs opacity-60'>{e.ts}</span>
                    <Badge variant='outline' className='h-4 shrink-0 px-1 py-0 text-[10px]'>{e.phase}</Badge>
                    <span className='text-foreground'>{e.detail || e.event}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </Main>
    </>
  )
}
