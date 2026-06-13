import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { ContentSection } from '../components/content-section'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Eye, EyeOff, ShieldCheck, Key, Sliders, FlaskConical, RefreshCw } from 'lucide-react'

// ─── 账号密码配置区 ───────────────────────────────────────────

function CredentialsSection() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null)

  const { data: credStatus, refetch: refetchCred } = useQuery({
    queryKey: ['credentials-status'],
    queryFn: api.getCredentialStatus,
    staleTime: 30_000,
  })

  const saveMutation = useMutation({
    mutationFn: () => api.saveCredentials(email, password),
    onSuccess: (res) => {
      toast.success(`账号已保存 (${res.email})`)
      setPassword('')
      refetchCred()
      queryClient.invalidateQueries({ queryKey: ['credentials-status'] })
    },
    onError: (e: Error) => toast.error(`保存失败: ${e.message}`),
  })

  const testMutation = useMutation({
    mutationFn: () => api.testLogin(email, password),
    onSuccess: (res) => setTestResult(res),
    onError: (e: Error) => setTestResult({ status: 'error', message: e.message }),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Key className='h-4 w-4' />
          Brain 账号凭证
          {credStatus?.configured
            ? <Badge variant='default' className='text-xs'>已配置</Badge>
            : <Badge variant='secondary' className='text-xs'>未配置</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-4'>
        {credStatus?.configured && (
          <p className='text-sm text-muted-foreground'>
            当前账号：<span className='font-mono text-foreground'>{credStatus.email}</span>
          </p>
        )}

        <div className='grid gap-3'>
          <div className='space-y-1.5'>
            <Label className='text-xs'>邮箱 (Email)</Label>
            <Input
              type='email'
              placeholder='your@email.com'
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className='h-9 text-sm'
            />
          </div>
          <div className='space-y-1.5'>
            <Label className='text-xs'>密码 (Password)</Label>
            <div className='relative'>
              <Input
                type={showPw ? 'text' : 'password'}
                placeholder='••••••••'
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className='h-9 text-sm pr-9'
              />
              <button
                type='button'
                className='absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground'
                onClick={() => setShowPw(!showPw)}
              >
                {showPw ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
              </button>
            </div>
          </div>
        </div>

        <div className='flex gap-2'>
          <Button
            size='sm'
            disabled={!email || !password || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            <ShieldCheck className='mr-1.5 h-3.5 w-3.5' />
            {saveMutation.isPending ? '保存中…' : '保存账号'}
          </Button>
          <Button
            size='sm'
            variant='outline'
            disabled={!email || !password || testMutation.isPending}
            onClick={() => { setTestResult(null); testMutation.mutate() }}
          >
            {testMutation.isPending ? '测试中…' : '测试登录'}
          </Button>
        </div>

        {testResult && (
          <div className={`rounded-md p-3 text-sm ${testResult.status === 'ok' ? 'bg-green-50 text-green-700 dark:bg-green-950/20 dark:text-green-400' : 'bg-red-50 text-red-700 dark:bg-red-950/20 dark:text-red-400'}`}>
            {testResult.message}
          </div>
        )}

        <p className='text-xs text-muted-foreground'>
          凭证保存到服务器的 <code>credentials.json</code>（不入 git）。
        </p>
      </CardContent>
    </Card>
  )
}

// ─── 挖掘参数配置区 ───────────────────────────────────────────

function DiggingConfigSection() {
  const queryClient = useQueryClient()
  const { data: cfg, isLoading, refetch } = useQuery({
    queryKey: ['full-config'],
    queryFn: api.getFullConfig,
    staleTime: 10_000,
  })

  const [form, setForm] = useState<Record<string, unknown>>({})
  const hasEdits = Object.keys(form).length > 0

  const saveMutation = useMutation({
    mutationFn: () => api.patchConfig(form),
    onSuccess: () => {
      toast.success('配置已保存')
      setForm({})
      refetch()
      queryClient.invalidateQueries({ queryKey: ['digging-config'] })
    },
    onError: (e: Error) => toast.error(`保存失败: ${e.message}`),
  })

  function set(k: string, v: unknown) {
    setForm((p) => ({ ...p, [k]: v }))
  }

  function val(k: string, fallback: unknown) {
    return k in form ? form[k] : (cfg?.digging?.[k] ?? fallback)
  }

  if (isLoading) return <Card><CardContent className='pt-4 text-sm text-muted-foreground'>加载配置中…</CardContent></Card>

  return (
    <Card>
      <CardHeader>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Sliders className='h-4 w-4' />
          挖掘参数
          {hasEdits && <Badge variant='secondary' className='text-xs'>{Object.keys(form).length} 项待保存</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-4'>
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>

          <div className='space-y-1.5'>
            <Label className='text-xs'>Dataset ID</Label>
            <Input
              className='h-9 text-sm font-mono'
              value={String(val('dataset_id', 'fundamental6'))}
              onChange={(e) => set('dataset_id', e.target.value)}
              placeholder='fundamental6'
            />
          </div>

          <div className='space-y-1.5'>
            <Label className='text-xs'>Region</Label>
            <Select value={String(val('region', 'USA'))} onValueChange={(v) => set('region', v)}>
              <SelectTrigger className='h-9 text-sm'><SelectValue /></SelectTrigger>
              <SelectContent>
                {['USA', 'EUR', 'ASI', 'GLB'].map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className='space-y-1.5'>
            <Label className='text-xs'>Universe</Label>
            <Select value={String(val('universe', 'TOP3000'))} onValueChange={(v) => set('universe', v)}>
              <SelectTrigger className='h-9 text-sm'><SelectValue /></SelectTrigger>
              <SelectContent>
                {['TOP3000', 'TOP2000', 'TOP1000', 'TOP500'].map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className='space-y-1.5'>
            <Label className='text-xs'>Delay <span className='text-muted-foreground'>(0=当天, 1=次日推荐)</span></Label>
            <Select value={String(val('delay', 1))} onValueChange={(v) => set('delay', parseInt(v))}>
              <SelectTrigger className='h-9 text-sm'><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value='0'>0 — 当天交易（门槛高）</SelectItem>
                <SelectItem value='1'>1 — 次日交易（推荐）</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className='space-y-1.5'>
            <Label className='text-xs'>Decay <span className='text-muted-foreground'>(1–21，基本面建议6–10)</span></Label>
            <Input
              type='number' min={1} max={21}
              className='h-9 text-sm font-mono'
              value={String(val('decay', 6))}
              onChange={(e) => set('decay', parseInt(e.target.value) || 6)}
            />
          </div>

          <div className='space-y-1.5'>
            <Label className='text-xs'>Neutralization</Label>
            <Select value={String(val('neutralization', 'SUBINDUSTRY'))} onValueChange={(v) => set('neutralization', v)}>
              <SelectTrigger className='h-9 text-sm'><SelectValue /></SelectTrigger>
              <SelectContent>
                {['MARKET', 'SECTOR', 'INDUSTRY', 'SUBINDUSTRY'].map(n => <SelectItem key={n} value={n}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className='space-y-1.5'>
            <Label className='text-xs'>并发数 (n_jobs)</Label>
            <Input
              type='number' min={1} max={20}
              className='h-9 text-sm font-mono'
              value={String(val('n_jobs', 3))}
              onChange={(e) => set('n_jobs', parseInt(e.target.value) || 3)}
            />
          </div>

          <div className='flex items-center justify-between pt-5'>
            <div>
              <Label className='text-xs'>Early Score Mode</Label>
              <p className='text-xs text-muted-foreground mt-0.5'>开启时优先探索高分因子</p>
            </div>
            <Switch
              checked={Boolean(val('early_score_mode', true))}
              onCheckedChange={(v) => set('early_score_mode', v)}
            />
          </div>

        </div>

        {/* check 模式 */}
        <div className='pt-2 border-t'>
          <Label className='text-xs'>提交前相关性检查模式</Label>
          <div className='flex gap-2 mt-2'>
            {(['FAST', 'OFFICIAL'] as const).map((m) => (
              <button
                key={m}
                className={`rounded border px-3 py-1.5 text-xs font-semibold font-mono transition-colors
                  ${String(val('check_mode', 'OFFICIAL')) === m
                    ? 'border-green-500 bg-green-500/15 text-green-400'
                    : 'border-border text-muted-foreground hover:border-green-500/50 hover:text-green-400'}`}
                onClick={() => set('check_mode', m)}
              >
                {m}
              </button>
            ))}
          </div>
          <p className='mt-1.5 text-xs text-muted-foreground'>
            {String(val('check_mode', 'OFFICIAL')) === 'FAST'
              ? 'FAST — xin_plus 近似粗筛，不调官方接口，速度最快'
              : 'OFFICIAL — xin_plus 粗筛 → 本地 PnL 剪枝 → 官方 self-corr（推荐）'}
          </p>
        </div>

        <div className='flex items-center gap-3 pt-2'>
          <Button
            size='sm'
            disabled={!hasEdits || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? '保存中…' : '保存配置'}
          </Button>
          <Button
            size='sm'
            variant='ghost'
            disabled={!hasEdits}
            onClick={() => setForm({})}
          >
            撤销修改
          </Button>
          <Button size='sm' variant='ghost' onClick={() => refetch()}>
            <RefreshCw className='h-3.5 w-3.5' />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── 当前 Tag 展示区 ──────────────────────────────────────────

function TagsSection() {
  const { data: cfg } = useQuery({
    queryKey: ['full-config'],
    queryFn: api.getFullConfig,
    staleTime: 10_000,
  })

  const { data: experiments } = useQuery({
    queryKey: ['experiments'],
    queryFn: api.getExperiments,
    staleTime: 10_000,
  })

  const tags = cfg?.tags ?? {}
  const active = cfg?.active_experiment ?? experiments?.active ?? ''

  return (
    <Card>
      <CardHeader>
        <CardTitle className='flex items-center gap-2 text-base'>
          <FlaskConical className='h-4 w-4' />
          当前 Tag 映射
          {active && <Badge variant='outline' className='text-xs font-mono'>{active}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className='grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3'>
          {Object.entries(tags).map(([k, v]) => (
            <div key={k} className='space-y-0.5'>
              <p className='text-xs text-muted-foreground'>{k}</p>
              <p className='font-mono text-xs bg-muted rounded px-2 py-0.5 break-all'>{v || '—'}</p>
            </div>
          ))}
        </div>
        <p className='mt-3 text-xs text-muted-foreground'>
          实验切换已废弃；当前统一使用 baseline 阶段 tag。需要改变挖掘范围时，请在上方修改 dataset/region/delay 等参数。
        </p>
      </CardContent>
    </Card>
  )
}

// ─── 主页面 ───────────────────────────────────────────────────

export function SettingsProfile() {
  return (
    <ContentSection
      title='系统配置'
      desc='账号密码、挖掘参数和 Tag 管理'
    >
      <div className='space-y-6'>
        <CredentialsSection />
        <DiggingConfigSection />
        <TagsSection />
      </div>
    </ContentSection>
  )
}
