import { useQuery } from '@tanstack/react-query'
import { api, type PlatformAlphaItem } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ThemeSwitch } from '@/components/theme-switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { RefreshCw, Globe, AlertCircle, ExternalLink } from 'lucide-react'

function fmtNum(v: number | null | undefined, digits = 2) {
  if (v == null || Number.isNaN(v)) return '—'
  if (Number.isInteger(v)) return v.toLocaleString()
  return v.toFixed(digits)
}

function fmtCount(v: number | null | undefined, capped = false) {
  if (v == null || v < 0) return '—'
  return capped ? `${v.toLocaleString()}+` : v.toLocaleString()
}

function ColorBadge({ color }: { color: string | null }) {
  if (!color) return <Badge variant='outline' className='text-[10px]'>无标记</Badge>
  const lower = color.toLowerCase()
  const cls = lower.includes('green')
    ? 'border-green-500 text-green-500'
    : lower.includes('red')
      ? 'border-red-500 text-red-500'
      : 'border-yellow-500 text-yellow-500'
  return <Badge variant='outline' className={`text-[10px] ${cls}`}>{color}</Badge>
}

function MetricCard({ label, value, note }: { label: string; value: string | number; note: string }) {
  return (
    <Card>
      <CardContent className='pt-4'>
        <p className='text-3xl font-bold text-primary'>{value}</p>
        <p className='text-sm font-medium mt-1'>{label}</p>
        <p className='text-xs text-muted-foreground'>{note}</p>
      </CardContent>
    </Card>
  )
}

function AlphaRow({ alpha }: { alpha: PlatformAlphaItem }) {
  return (
    <tr className='border-b text-xs hover:bg-muted/40'>
      <td className='px-3 py-2 font-mono text-primary'>
        <a
          href={`https://platform.worldquantbrain.com/alpha/${alpha.id}`}
          target='_blank'
          rel='noreferrer'
          className='inline-flex items-center gap-1 hover:underline'
        >
          {alpha.id}<ExternalLink className='h-3 w-3' />
        </a>
      </td>
      <td className='px-3 py-2'><Badge variant='secondary' className='text-[10px]'>{alpha.stage || '—'}</Badge></td>
      <td className='px-3 py-2'>{alpha.status || '—'}</td>
      <td className='px-3 py-2'><ColorBadge color={alpha.color} /></td>
      <td className='px-3 py-2 text-right font-mono'>{fmtNum(alpha.sharpe)}</td>
      <td className='px-3 py-2 text-right font-mono'>{fmtNum(alpha.fitness)}</td>
      <td className='px-3 py-2 text-right font-mono'>{fmtNum(alpha.turnover)}</td>
      <td className='px-3 py-2 text-right font-mono'>{fmtNum(alpha.returns)}</td>
      <td className='px-3 py-2'>{alpha.region || '—'} / {alpha.universe || '—'}</td>
      <td className='px-3 py-2 font-mono'>{alpha.dateCreated?.slice(0, 10) || '—'}</td>
      <td className='px-3 py-2 max-w-[220px] truncate font-mono text-[10px] text-muted-foreground'>
        {(alpha.tags ?? []).join(', ') || '—'}
      </td>
    </tr>
  )
}

export function PlatformAlphas() {
  const {
    data: overview,
    isLoading: overviewLoading,
    isError: overviewIsError,
    error: overviewError,
    refetch: refetchOverview,
  } = useQuery({
    queryKey: ['platform-overview'],
    queryFn: api.getPlatformOverview,
    retry: 1,
    staleTime: 60_000,
  })

  const {
    data: alphas,
    isLoading: alphasLoading,
    isError: alphasIsError,
    error: alphasError,
    refetch: refetchAlphas,
  } = useQuery({
    queryKey: ['platform-alphas', 'OS'],
    queryFn: () => api.getPlatformAlphas({ stage: 'OS', limit: 50, order: '-dateCreated' }),
    retry: 1,
    staleTime: 30_000,
  })

  const loading = overviewLoading || alphasLoading
  const overviewMessage = overviewError instanceof Error ? overviewError.message : String(overviewError ?? '')
  const alphasMessage = alphasError instanceof Error ? alphasError.message : String(alphasError ?? '')

  return (
    <>
      <Header>
        <div className='ml-auto flex items-center gap-2'>
          <Button variant='outline' size='sm' onClick={() => { refetchOverview(); refetchAlphas() }}>
            <RefreshCw className={`mr-1 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </Button>
          <ThemeSwitch />
        </div>
      </Header>

      <Main>
        <div className='mb-6'>
          <h1 className='text-2xl font-bold tracking-tight'>平台 Alpha</h1>
          <p className='text-sm text-muted-foreground'>来自 WorldQuant BRAIN 平台的真实账号和因子数据</p>
        </div>

        {overviewIsError ? (
          <Card className='mb-6 border-red-500/30'>
            <CardContent className='flex items-start gap-3 py-6 text-sm'>
              <AlertCircle className='mt-0.5 h-5 w-5 shrink-0 text-red-500' />
              <div>
                <p className='font-medium text-red-500'>平台总览加载失败</p>
                <p className='mt-1 text-muted-foreground'>{overviewMessage}</p>
                <p className='mt-1 text-xs text-muted-foreground'>请先在设置页配置 credentials.json，或确认 Brain 平台连接正常。</p>
              </div>
            </CardContent>
          </Card>
        ) : overview ? (
          <>
            <div className='mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground'>
              <Globe className='h-3.5 w-3.5' />
              <span>账号 <span className='font-mono text-foreground'>{overview.full_name || '—'}</span> ({overview.user_id || '—'})</span>
              <span>·</span>
              <span>抓取时间 <span className='font-mono text-foreground'>{overview.fetched_at || '—'}</span></span>
            </div>
            <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-5 mb-6'>
              <MetricCard label='Genius 等级' value={overview.genius_level || '—'} note='平台账号等级' />
              <MetricCard label='OS 数量' value={fmtCount(overview.alphas_os_count, overview.os_capped)} note='已通过/计入 weight' />
              <MetricCard label='IS 数量' value={fmtCount(overview.alphas_is_count, overview.is_capped)} note='回测中/待审阶段' />
              <MetricCard label='未提交' value={fmtCount(overview.unsubmitted_count, overview.unsubmitted_capped)} note='IS + UNSUBMITTED' />
              <MetricCard label='总计' value={fmtCount(overview.total_alphas, overview.is_capped || overview.unsubmitted_capped)} note='各阶段合计' />
            </div>
            {overview.stage_counts && (
              <Card className='mb-6'>
                <CardHeader className='pb-2'><CardTitle className='text-base'>平台阶段计数</CardTitle></CardHeader>
                <CardContent className='flex flex-wrap gap-2 text-xs'>
                  {Object.entries(overview.stage_counts).map(([stage, count]) => (
                    <Badge key={stage} variant='outline' className='font-mono'>{stage}: {fmtCount(count)}</Badge>
                  ))}
                  <Badge variant='secondary' className='font-mono'>TOTAL: {fmtCount(overview.total_alphas)}</Badge>
                </CardContent>
              </Card>
            )}
          </>
        ) : (
          <Card className='mb-6'>
            <CardContent className='flex flex-col items-center gap-3 py-12 text-muted-foreground'>
              <Globe className='h-10 w-10 opacity-40' />
              <p className='text-sm'>平台数据加载中…</p>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className='flex items-center justify-between text-base'>
              <span>平台 OS 因子列表（最近 50 个）</span>
              {alphas && <Badge variant='outline' className='font-mono text-xs'>total {fmtCount(alphas.total)}</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {alphasIsError ? (
              <div className='flex items-start gap-3 rounded-md border border-red-500/30 p-4 text-sm'>
                <AlertCircle className='mt-0.5 h-5 w-5 shrink-0 text-red-500' />
                <div>
                  <p className='font-medium text-red-500'>平台因子列表加载失败</p>
                  <p className='mt-1 text-muted-foreground'>{alphasMessage}</p>
                </div>
              </div>
            ) : alphasLoading ? (
              <p className='py-8 text-center text-sm text-muted-foreground'>加载平台因子中…</p>
            ) : alphas?.items?.length ? (
              <div className='overflow-auto rounded-md border'>
                <table className='w-full min-w-[960px] border-collapse'>
                  <thead className='bg-muted/70 text-xs text-muted-foreground'>
                    <tr>
                      <th className='px-3 py-2 text-left'>ID</th>
                      <th className='px-3 py-2 text-left'>Stage</th>
                      <th className='px-3 py-2 text-left'>Status</th>
                      <th className='px-3 py-2 text-left'>Color</th>
                      <th className='px-3 py-2 text-right'>Sharpe</th>
                      <th className='px-3 py-2 text-right'>Fitness</th>
                      <th className='px-3 py-2 text-right'>Turnover</th>
                      <th className='px-3 py-2 text-right'>Returns</th>
                      <th className='px-3 py-2 text-left'>Region/Universe</th>
                      <th className='px-3 py-2 text-left'>Created</th>
                      <th className='px-3 py-2 text-left'>Tags</th>
                    </tr>
                  </thead>
                  <tbody>{alphas.items.map((alpha) => <AlphaRow key={alpha.id} alpha={alpha} />)}</tbody>
                </table>
              </div>
            ) : (
              <p className='text-sm text-muted-foreground py-8 text-center'>暂无平台 OS 因子数据</p>
            )}
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
