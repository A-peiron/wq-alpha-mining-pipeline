import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ThemeSwitch } from '@/components/theme-switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
  ScatterChart, Scatter, ZAxis,
  Cell,
} from 'recharts'
import { RefreshCw } from 'lucide-react'

const STEP_COLORS: Record<string, string> = {
  '1step': '#3b82f6',
  '2step': '#a855f7',
  '3step': '#f97316',
  unknown: '#64748b',
}

function fmt(v: number | null | undefined, d = 4): string {
  if (v == null) return '—'
  return Number(v).toFixed(d)
}

type TabKey = 'funnel' | 'distribution' | 'timeline' | 'scatter' | 'top'

export function Analysis() {
  const [tab, setTab] = useState<TabKey>('funnel')
  const [days, setDays] = useState(14)
  const [topSort, setTopSort] = useState('sharpe')
  const [topTag, setTopTag] = useState('')

  const { data: funnel, refetch: refetchFunnel } = useQuery({
    queryKey: ['funnel'],
    queryFn: api.getFunnel,
    staleTime: 30_000,
  })

  const { data: dist } = useQuery({
    queryKey: ['distribution'],
    queryFn: () => api.getDistribution(),
    staleTime: 30_000,
  })

  const { data: timeline, refetch: refetchTimeline } = useQuery({
    queryKey: ['timeline', days],
    queryFn: () => api.getTimeline(days),
    staleTime: 15_000,
  })

  const { data: scatter } = useQuery({
    queryKey: ['scatter'],
    queryFn: () => api.getScatter(),
    staleTime: 30_000,
  })

  const { data: topData } = useQuery({
    queryKey: ['top-alphas', topSort, topTag],
    queryFn: () => api.getTopAlphas({ n: 50, sort: topSort, tag: topTag || undefined }),
    staleTime: 15_000,
  })

  function reload() { refetchFunnel(); refetchTimeline() }

  const TABS: { key: TabKey; label: string }[] = [
    { key: 'funnel', label: '挖掘漏斗' },
    { key: 'distribution', label: 'Sharpe/Fitness 分布' },
    { key: 'timeline', label: '产出时间线' },
    { key: 'scatter', label: '指标散点图' },
    { key: 'top', label: 'Top 因子表' },
  ]

  const funnelByStepData = funnel
    ? Object.entries(funnel.by_step).map(([step, d]) => ({ step, total: d.total, success: d.success }))
    : []

  const shareChartData = dist ? Object.entries(dist.sharpe).map(([k, v]) => ({ range: k, count: v })) : []
  const fitnessChartData = dist ? Object.entries(dist.fitness).map(([k, v]) => ({ range: k, count: v })) : []

  const timelineChartData = timeline
    ? timeline.dates.map((d, i) => {
        const row: Record<string, unknown> = { date: d.slice(5) }
        Object.entries(timeline.series).forEach(([step, data]) => { row[step] = data[i] ?? 0 })
        return row
      })
    : []

  const scatterDataByStep: Record<string, Array<{ x: number; y: number; z: number; code: string }>> = {}
  for (const p of scatter?.points ?? []) {
    if (!scatterDataByStep[p.step]) scatterDataByStep[p.step] = []
    scatterDataByStep[p.step].push({
      x: p.sharpe,
      y: p.fitness,
      z: Math.max(30, Math.min(300, (p.turnover ?? 0.1) * 800)),
      code: p.code,
    })
  }

  return (
    <>
      <Header>
        <div className='ml-auto flex items-center gap-2'>
          <Button variant='outline' size='sm' onClick={reload}><RefreshCw className='mr-1 h-3.5 w-3.5' />刷新</Button>
          <ThemeSwitch />
        </div>
      </Header>

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>数据分析</h1>
          <p className='text-sm text-muted-foreground'>Mining Analytics · {new Date().toLocaleDateString('zh-CN')}</p>
        </div>

        <div className='flex gap-1 bg-muted/40 border rounded-lg p-1 mb-6 flex-wrap'>
          {TABS.map((t) => (
            <button key={t.key} className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${tab === t.key ? 'bg-background shadow text-foreground' : 'text-muted-foreground hover:text-foreground'}`} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'funnel' && (
          <div className='space-y-4'>
            <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
              {[
                { label: '总模拟次数', value: funnel?.total },
                { label: '成功模拟', value: funnel?.success },
                { label: '重复跳过', value: funnel?.duplicated },
                { label: '通过 Check', value: funnel?.passed_check },
              ].map(({ label, value }) => (
                <Card key={label}><CardContent className='pt-4'>
                  <p className='text-2xl font-bold font-mono'>{value?.toLocaleString() ?? '—'}</p>
                  <p className='text-xs text-muted-foreground mt-1'>{label}</p>
                </CardContent></Card>
              ))}
            </div>
            <Card>
              <CardHeader><CardTitle className='text-base'>按阶段分组</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width='100%' height={200}>
                  <BarChart data={funnelByStepData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <XAxis dataKey='step' tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey='total' name='总模拟' radius={[3, 3, 0, 0]}>
                      {funnelByStepData.map((e) => <Cell key={e.step} fill={`${STEP_COLORS[e.step] ?? '#64748b'}80`} stroke={STEP_COLORS[e.step] ?? '#64748b'} strokeWidth={1} />)}
                    </Bar>
                    <Bar dataKey='success' name='成功' radius={[3, 3, 0, 0]}>
                      {funnelByStepData.map((e) => <Cell key={e.step} fill={STEP_COLORS[e.step] ?? '#64748b'} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        )}

        {tab === 'distribution' && (
          <div className='space-y-4'>
            {dist && <p className='text-sm text-muted-foreground'>共 <strong>{dist.total}</strong> 个通过 Check 的因子</p>}
            <div className='grid gap-4 lg:grid-cols-2'>
              <Card><CardHeader><CardTitle className='text-base'>Sharpe 分布</CardTitle></CardHeader><CardContent>
                <ResponsiveContainer width='100%' height={220}>
                  <BarChart data={shareChartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <XAxis dataKey='range' tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip />
                    <Bar dataKey='count' name='数量' fill='#3b82f6' radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent></Card>
              <Card><CardHeader><CardTitle className='text-base'>Fitness 分布</CardTitle></CardHeader><CardContent>
                <ResponsiveContainer width='100%' height={220}>
                  <BarChart data={fitnessChartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <XAxis dataKey='range' tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip />
                    <Bar dataKey='count' name='数量' fill='#a855f7' radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent></Card>
            </div>
          </div>
        )}

        {tab === 'timeline' && (
          <div className='space-y-4'>
            <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger className='w-28'><SelectValue /></SelectTrigger>
              <SelectContent>
                {[7, 14, 30].map((d) => <SelectItem key={d} value={String(d)}>{d} 天</SelectItem>)}
              </SelectContent>
            </Select>
            <Card><CardHeader><CardTitle className='text-base'>每日新增通过 Check 因子数</CardTitle></CardHeader><CardContent>
              <ResponsiveContainer width='100%' height={260}>
                <LineChart data={timelineChartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <XAxis dataKey='date' tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  {Object.keys(timeline?.series ?? {}).map((step) => (
                    <Line key={step} type='monotone' dataKey={step} stroke={STEP_COLORS[step] ?? '#64748b'} dot={false} strokeWidth={1.5} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </CardContent></Card>
          </div>
        )}

        {tab === 'scatter' && (
          <Card>
            <CardHeader><CardTitle className='text-base'>Sharpe vs Fitness (点大小代表 Turnover)</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width='100%' height={320}>
                <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <XAxis type='number' dataKey='x' name='Sharpe' tick={{ fontSize: 10 }} label={{ value: 'Sharpe', position: 'insideBottom', offset: -4, fontSize: 11 }} />
                  <YAxis type='number' dataKey='y' name='Fitness' tick={{ fontSize: 10 }} label={{ value: 'Fitness', angle: -90, position: 'insideLeft', fontSize: 11 }} />
                  <ZAxis type='number' dataKey='z' range={[20, 300]} />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ payload }) => {
                    if (!payload?.length) return null
                    const d = payload[0]?.payload
                    return <div className='rounded border bg-background p-2 text-xs'><p>Sharpe: {d?.x?.toFixed(3)}</p><p>Fitness: {d?.y?.toFixed(3)}</p><p className='text-muted-foreground truncate max-w-48'>{d?.code}</p></div>
                  }} />
                  <Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  {Object.entries(scatterDataByStep).map(([step, data]) => (
                    <Scatter key={step} name={step} data={data} fill={`${STEP_COLORS[step] ?? '#64748b'}cc`} />
                  ))}
                </ScatterChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {tab === 'top' && (
          <div className='space-y-4'>
            <div className='flex flex-wrap gap-3'>
              <Select value={topSort} onValueChange={setTopSort}>
                <SelectTrigger className='w-36'><SelectValue placeholder='排序' /></SelectTrigger>
                <SelectContent>
                  <SelectItem value='sharpe'>Sharpe</SelectItem>
                  <SelectItem value='fitness'>Fitness</SelectItem>
                  <SelectItem value='turnover'>Turnover ↑</SelectItem>
                  <SelectItem value='self_corr'>Self-Corr ↑</SelectItem>
                </SelectContent>
              </Select>
              <Input className='w-32' placeholder='Tag 过滤' value={topTag} onChange={(e) => setTopTag(e.target.value)} />
            </div>
            <Card>
              <CardHeader><CardTitle className='text-base'>共 {topData?.total ?? 0} 个 · 显示前 {topData?.items.length ?? 0} 个</CardTitle></CardHeader>
              <CardContent className='p-0 overflow-x-auto'>
                <table className='w-full text-sm border-collapse'>
                  <thead>
                    <tr className='border-b text-left text-xs text-muted-foreground'>
                      <th className='px-4 py-2'>表达式</th>
                      <th className='px-2 py-2'>Tags</th>
                      <th className='px-2 py-2 text-right'>Sharpe</th>
                      <th className='px-2 py-2 text-right'>Fitness</th>
                      <th className='px-2 py-2 text-right'>Turnover</th>
                      <th className='px-2 py-2 text-right'>Self-Corr</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(topData?.items ?? []).map((a, i) => (
                      <tr key={a.id ?? i} className='border-b hover:bg-muted/30'>
                        <td className='px-4 py-2'><code className='text-xs truncate block max-w-xs'>{a.code}</code></td>
                        <td className='px-2 py-2'><span className='text-xs bg-purple-500/15 text-purple-400 rounded px-1.5 py-0.5'>{(a.tags ?? '').split(',').find((t) => t.includes('step')) || '—'}</span></td>
                        <td className={`px-2 py-2 text-right font-mono text-xs ${Math.abs(a.sharpe ?? 0) >= 1.5 ? 'text-green-500 font-bold' : Math.abs(a.sharpe ?? 0) >= 1.25 ? 'text-yellow-500' : ''}`}>{fmt(a.sharpe)}</td>
                        <td className={`px-2 py-2 text-right font-mono text-xs ${Math.abs(a.fitness ?? 0) >= 1.0 ? 'text-green-500 font-bold' : ''}`}>{fmt(a.fitness)}</td>
                        <td className='px-2 py-2 text-right font-mono text-xs'>{a.turnover != null ? `${(a.turnover * 100).toFixed(1)}%` : '—'}</td>
                        <td className={`px-2 py-2 text-right font-mono text-xs ${(a.self_corr ?? 0) > 0.6 ? 'text-red-500' : ''}`}>{fmt(a.self_corr, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>
        )}
      </Main>
    </>
  )
}
