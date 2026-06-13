import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ThemeSwitch } from '@/components/theme-switch'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Bot } from 'lucide-react'

export function AgentPage() {
  return (
    <>
      <Header>
        <div className='ml-auto flex items-center gap-2'>
          <ThemeSwitch />
        </div>
      </Header>

      <Main>
        <div className='mb-6'>
          <h1 className='text-2xl font-bold tracking-tight'>AI Agent</h1>
          <p className='text-sm text-muted-foreground'>智能因子分析与优化建议（规划中）</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className='flex items-center gap-2 text-base'>
              <Bot className='h-4 w-4' />
              AI 优化功能
            </CardTitle>
          </CardHeader>
          <CardContent className='flex flex-col items-center gap-4 py-12 text-center text-muted-foreground'>
            <Bot className='h-16 w-16 opacity-20' />
            <p className='text-lg font-medium'>AI Agent 功能尚未启用</p>
            <p className='text-sm max-w-md'>
              当前阶段 AI 优化闭环未开启。若后续集成 DeepSeek API，可在此页面触发因子策略分析和优化建议，但最终提交仍由人工决策。
            </p>
            <div className='rounded-lg border border-dashed p-4 text-xs font-mono text-muted-foreground'>
              POST /api/agent/analyze → 501 Not Implemented
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
