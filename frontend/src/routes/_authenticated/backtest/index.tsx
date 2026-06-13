import { createFileRoute } from '@tanstack/react-router'
import { Analysis } from '@/features/backtest'

export const Route = createFileRoute('/_authenticated/backtest/')({
  component: Analysis,
})
