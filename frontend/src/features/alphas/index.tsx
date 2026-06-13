import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, type AlphaItem } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ThemeSwitch } from '@/components/theme-switch'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { RefreshCw, ChevronDown, ChevronUp, ExternalLink, Send, ShieldCheck } from 'lucide-react'

// ─── 信号灯与质量 Badge ───────────────────────────────────────

const SIGNAL_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  GREEN: 'default', YELLOW: 'secondary', RED: 'destructive', DEAD: 'outline',
}
const SIGNAL_EMOJI: Record<string, string> = {
  GREEN: '🟢', YELLOW: '🟡', RED: '🔴', DEAD: '⚫',
}

function QualityBadge({ signal }: { signal: string | null }) {
  if (!signal) return <span className='text-muted-foreground'>—</span>
  return (
    <Badge variant={SIGNAL_VARIANT[signal] ?? 'outline'}>
      {SIGNAL_EMOJI[signal]} {signal}
    </Badge>
  )
}

function ReviewBadge({ status }: { status: string | null }) {
  if (!status || status === 'pending') {
    return <span className='rounded px-1.5 py-0.5 text-xs bg-yellow-500/15 text-yellow-500'>待审核</span>
  }
  return <span className='rounded px-1.5 py-0.5 text-xs bg-muted text-muted-foreground'>{status}</span>
}

function QualityStatusBadge({ qs }: { qs: string | null }) {
  if (!qs) return <span className='text-muted-foreground'>—</span>
  const map: Record<string, string> = {
    PASS: 'bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400',
    OPTIMIZE: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-950/30 dark:text-yellow-400',
    REJECT: 'bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400',
  }
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${map[qs] ?? 'bg-muted text-muted-foreground'}`}>
      {qs}
    </span>
  )
}

function fmt(v: number | null | undefined, d = 4): string {
  if (v == null) return '—'
  return Number(v).toFixed(d)
}

// ─── 展开行：详细指标 + 操作 ──────────────────────────────────

function AlphaExpandRow({ alpha, colSpan }: { alpha: AlphaItem; colSpan: number }) {
  const queryClient = useQueryClient()
  const [reviewStatus, setReviewStatus] = useState(alpha.review_status ?? 'pending')
  const [reviewNote, setReviewNote] = useState(alpha.review_note ?? '')
  const [officialChecks, setOfficialChecks] = useState<Array<{ name: string; result: string; value?: number }>>([])
  const [checkLoading, setCheckLoading] = useState(false)

  const submitMutation = useMutation({
    mutationFn: () => api.submitAlpha(alpha.id),
    onSuccess: (res) => {
      if (res.status === 'ok') {
        toast.success(`${alpha.id.slice(0, 8)} 提交成功`)
        queryClient.invalidateQueries({ queryKey: ['alphas'] })
      } else {
        toast.error(res.message)
      }
    },
    onError: (e: Error) => toast.error(`提交失败: ${e.message}`),
  })

  const reviewMutation = useMutation({
    mutationFn: () => api.updateReview(alpha.id, { review_status: reviewStatus, review_note: reviewNote }),
    onSuccess: () => {
      toast.success('审核状态已保存')
      queryClient.invalidateQueries({ queryKey: ['alphas'] })
    },
    onError: (e: Error) => toast.error(`保存失败: ${e.message}`),
  })

  async function handleOfficialCheck() {
    setCheckLoading(true)
    try {
      const res = await api.officialCheck(alpha.id)
      setOfficialChecks(res.checks ?? [])
    } catch (e: any) {
      toast.error(`检查失败: ${e.message}`)
    } finally {
      setCheckLoading(false)
    }
  }

  const brainUrl = `https://platform.worldquantbrain.com/alpha/${alpha.id}`
  return (
    <TableRow className='bg-muted/20'>
      <TableCell colSpan={colSpan} className='p-4'>
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm'>
          <div className='space-y-1.5'>
            <p className='text-xs font-semibold text-muted-foreground uppercase tracking-wider'>基础指标</p>
            {[
              { label: 'Sharpe', value: fmt(alpha.sharpe) },
              { label: 'Fitness', value: fmt(alpha.fitness) },
              { label: 'Turnover', value: alpha.turnover != null ? `${(alpha.turnover * 100).toFixed(1)}%` : '—' },
              { label: 'Margin', value: fmt(alpha.margin, 2) },
              { label: 'Returns', value: fmt(alpha.returns) },
            ].map(({ label, value }) => (
              <div key={label} className='flex justify-between'>
                <span className='text-muted-foreground'>{label}</span>
                <span className='font-mono'>{value}</span>
              </div>
            ))}
          </div>
          <div className='space-y-1.5'>
            <p className='text-xs font-semibold text-muted-foreground uppercase tracking-wider'>相关性</p>
            {[
              { label: 'Self-Corr', value: fmt(alpha.self_corr, 3) },
              { label: 'Prod-Corr', value: fmt(alpha.prod_corr, 3) },
              { label: 'Fallback 使用', value: alpha.fallback_used ? '是' : '否' },
              { label: 'Official Check', value: alpha.official_check_status ?? '—' },
              { label: 'DSI 信号', value: alpha.dsi_signal ?? '—' },
            ].map(({ label, value }) => (
              <div key={label} className='flex justify-between'>
                <span className='text-muted-foreground'>{label}</span>
                <span className='font-mono'>{value}</span>
              </div>
            ))}
          </div>
          <div className='space-y-1.5'>
            <p className='text-xs font-semibold text-muted-foreground uppercase tracking-wider'>审核信息</p>
            {[
              { label: '质量状态', value: alpha.quality_status ?? '—' },
              { label: '信号灯', value: alpha.signal_light ?? '—' },
              { label: '质量层级', value: alpha.quality_tier ?? '—' },
              { label: '审核状态', value: alpha.review_status ?? '—' },
              { label: '审核备注', value: alpha.review_note || '—' },
            ].map(({ label, value }) => (
              <div key={label} className='flex justify-between'>
                <span className='text-muted-foreground'>{label}</span>
                <span className='font-mono text-xs'>{value}</span>
              </div>
            ))}
          </div>
          <div className='space-y-1.5'>
            <p className='text-xs font-semibold text-muted-foreground uppercase tracking-wider'>失败原因</p>
            <p className='text-xs text-muted-foreground break-all'>{alpha.quality_reasons || '无'}</p>
            <p className='text-xs font-semibold text-muted-foreground uppercase tracking-wider mt-2'>完整表达式</p>
            <code className='block text-xs break-all bg-muted rounded p-1.5'>{alpha.code}</code>
            {alpha.check_time && (
              <p className='text-xs text-muted-foreground'>Check 时间：{alpha.check_time}</p>
            )}
          </div>

          {/* 审核操作区 */}
          <div className='mt-4 pt-4 border-t space-y-3'>
            <div className='flex flex-wrap gap-2 items-center'>
              <Select value={reviewStatus} onValueChange={setReviewStatus}>
                <SelectTrigger className='h-7 w-32 text-xs'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='pending'>待审核</SelectItem>
                  <SelectItem value='approved'>已批准</SelectItem>
                  <SelectItem value='skipped'>已跳过</SelectItem>
                  <SelectItem value='blocked_by_corr'>高相关屏蔽</SelectItem>
                </SelectContent>
              </Select>
              <Input
                className='h-7 text-xs flex-1 min-w-32'
                placeholder='审核备注...'
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
              />
              <Button size='sm' variant='outline' className='h-7 text-xs' onClick={() => reviewMutation.mutate()} disabled={reviewMutation.isPending}>
                保存审核
              </Button>
            </div>
            <div className='flex flex-wrap gap-2'>
              <Button
                size='sm'
                className='h-7 text-xs bg-green-700 hover:bg-green-600 text-white'
                disabled={submitMutation.isPending}
                onClick={() => {
                  if (confirm(`确认提交 ${alpha.id} 到 Brain 平台？此操作不可撤销。`)) {
                    submitMutation.mutate()
                  }
                }}
              >
                <Send className='mr-1 h-3.5 w-3.5' />
                {submitMutation.isPending ? '提交中…' : '提交到 Brain'}
              </Button>
              <Button
                size='sm'
                variant='outline'
                className='h-7 text-xs'
                disabled={checkLoading}
                onClick={handleOfficialCheck}
              >
                <ShieldCheck className='mr-1 h-3.5 w-3.5' />
                {checkLoading ? '检查中…' : '官方回测检查'}
              </Button>
              <a href={brainUrl} target='_blank' rel='noreferrer'>
                <Button size='sm' variant='ghost' className='h-7 text-xs'>
                  <ExternalLink className='mr-1 h-3.5 w-3.5' />
                  Brain 平台
                </Button>
              </a>
            </div>
            {officialChecks.length > 0 && (
              <div className='mt-2 rounded border bg-muted/40 p-2 text-xs space-y-1'>
                <p className='font-semibold text-muted-foreground'>官方检查结果:</p>
                {officialChecks.map((c, i) => (
                  <div key={i} className={`flex justify-between ${c.result === 'FAIL' ? 'text-red-500' : c.result === 'PASS' ? 'text-green-500' : 'text-yellow-500'}`}>
                    <span>{c.name}</span>
                    <span className='font-mono'>{c.result}{c.value != null ? ` (${Number(c.value).toFixed(3)})` : ''}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ─── 主页面 ───────────────────────────────────────────────────

export function AlphaList() {
  const [signalFilter, setSignalFilter] = useState('all')
  const [qsFilter, setQsFilter] = useState('all')
  const [tagFilter, setTagFilter] = useState('')
  const [sortBy, setSortBy] = useState('sharpe')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['alphas'],
    queryFn: api.getAlphas,
    refetchInterval: 20_000,
  })

  const alphas = data?.alphas ?? []

  const filtered = alphas
    .filter((a) => signalFilter === 'all' || a.signal_light === signalFilter)
    .filter((a) => qsFilter === 'all' || a.quality_status === qsFilter)
    .filter((a) => !tagFilter || (a.tags ?? '').includes(tagFilter))
    .sort((a, b) => {
      const v = (x: AlphaItem) => {
        if (sortBy === 'sharpe') return Math.abs(x.sharpe ?? 0)
        if (sortBy === 'fitness') return Math.abs(x.fitness ?? 0)
        if (sortBy === 'margin') return x.margin ?? 0
        if (sortBy === 'self_corr') return -(x.self_corr ?? 1)
        if (sortBy === 'review_priority') return -(x.review_priority ?? 0)
        return 0
      }
      return v(b) - v(a)
    })

  const COL_SPAN = 9

  return (
    <>
      <Header>
        <div className='ml-auto flex items-center gap-2'>
          <ThemeSwitch />
        </div>
      </Header>

      <Main>
        <div className='mb-4 flex items-center justify-between'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>可提交因子</h1>
            <p className='text-sm text-muted-foreground'>共 {filtered.length} / {alphas.length} 个 · 点击行展开详情</p>
          </div>
          <Button variant='outline' size='sm' onClick={() => refetch()}>
            <RefreshCw className='mr-1 h-3.5 w-3.5' />
            刷新
          </Button>
        </div>

        {/* 过滤栏 */}
        <Card className='mb-4'>
          <CardContent className='flex flex-wrap gap-3 pt-4'>
            <Select value={signalFilter} onValueChange={setSignalFilter}>
              <SelectTrigger className='w-36'>
                <SelectValue placeholder='信号灯' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='all'>全部信号</SelectItem>
                <SelectItem value='GREEN'>🟢 GREEN</SelectItem>
                <SelectItem value='YELLOW'>🟡 YELLOW</SelectItem>
                <SelectItem value='RED'>🔴 RED</SelectItem>
                <SelectItem value='DEAD'>⚫ DEAD</SelectItem>
              </SelectContent>
            </Select>

            <Select value={qsFilter} onValueChange={setQsFilter}>
              <SelectTrigger className='w-36'>
                <SelectValue placeholder='质量状态' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='all'>全部</SelectItem>
                <SelectItem value='PASS'>PASS</SelectItem>
                <SelectItem value='OPTIMIZE'>OPTIMIZE</SelectItem>
                <SelectItem value='REJECT'>REJECT</SelectItem>
              </SelectContent>
            </Select>

            <Input
              className='w-36'
              placeholder='Tag 过滤 (如 2step)'
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
            />

            <Select value={sortBy} onValueChange={setSortBy}>
              <SelectTrigger className='w-36'>
                <SelectValue placeholder='排序' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='sharpe'>Sharpe ↓</SelectItem>
                <SelectItem value='fitness'>Fitness ↓</SelectItem>
                <SelectItem value='margin'>Margin ↓</SelectItem>
                <SelectItem value='self_corr'>Self-Corr ↑</SelectItem>
                <SelectItem value='review_priority'>审核优先级 ↓</SelectItem>
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className='text-base'>因子列表（来自 submitable_alpha.csv，仅供人工提交）</CardTitle>
          </CardHeader>
          <CardContent className='p-0'>
            <div className='overflow-x-auto'>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className='w-8' />
                    <TableHead>表达式</TableHead>
                    <TableHead className='text-right'>Sharpe</TableHead>
                    <TableHead className='text-right'>Fitness</TableHead>
                    <TableHead className='text-right'>Turnover</TableHead>
                    <TableHead className='text-right'>Self-Corr</TableHead>
                    <TableHead>信号灯</TableHead>
                    <TableHead>质量状态</TableHead>
                    <TableHead>审核状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    <TableRow>
                      <TableCell colSpan={COL_SPAN} className='py-8 text-center text-muted-foreground'>加载中…</TableCell>
                    </TableRow>
                  ) : filtered.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={COL_SPAN} className='py-8 text-center text-muted-foreground'>暂无数据</TableCell>
                    </TableRow>
                  ) : (
                    filtered.flatMap((alpha) => {
                      const isExpanded = expandedId === alpha.id
                      return [
                        <TableRow
                          key={alpha.id}
                          className='cursor-pointer hover:bg-muted/50'
                          onClick={() => setExpandedId(isExpanded ? null : alpha.id)}
                        >
                          <TableCell className='w-8 text-muted-foreground'>
                            {isExpanded ? <ChevronUp className='h-4 w-4' /> : <ChevronDown className='h-4 w-4' />}
                          </TableCell>
                          <TableCell className='max-w-xs'>
                            <code className='block truncate rounded bg-muted px-1 py-0.5 text-xs'>
                              {alpha.code}
                            </code>
                            <span className='mt-0.5 block text-xs text-muted-foreground'>
                              {alpha.region} D{alpha.delay} · {(alpha.tags ?? '').split(',').find((t) => t.includes('step')) ?? ''}
                            </span>
                          </TableCell>
                          <TableCell className={`text-right font-mono text-sm ${alpha.sharpe && Math.abs(alpha.sharpe) >= 1.25 ? 'font-semibold text-green-600' : ''}`}>
                            {fmt(alpha.sharpe)}
                          </TableCell>
                          <TableCell className={`text-right font-mono text-sm ${alpha.fitness && Math.abs(alpha.fitness) >= 1.0 ? 'font-semibold text-green-600' : ''}`}>
                            {fmt(alpha.fitness)}
                          </TableCell>
                          <TableCell className='text-right font-mono text-sm'>
                            {alpha.turnover != null ? `${(alpha.turnover * 100).toFixed(1)}%` : '—'}
                          </TableCell>
                          <TableCell className={`text-right font-mono text-sm ${(alpha.self_corr ?? 0) > 0.6 ? 'text-red-500' : ''}`}>
                            {fmt(alpha.self_corr, 3)}
                          </TableCell>
                          <TableCell><QualityBadge signal={alpha.signal_light} /></TableCell>
                          <TableCell><QualityStatusBadge qs={alpha.quality_status} /></TableCell>
                          <TableCell><ReviewBadge status={alpha.review_status} /></TableCell>
                        </TableRow>,
                        isExpanded && <AlphaExpandRow key={`exp-${alpha.id}`} alpha={alpha} colSpan={COL_SPAN} />,
                      ].filter(Boolean)
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
