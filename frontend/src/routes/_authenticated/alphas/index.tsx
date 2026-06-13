import { createFileRoute } from '@tanstack/react-router'
import { AlphaList } from '@/features/alphas'

export const Route = createFileRoute('/_authenticated/alphas/')({
  component: AlphaList,
})
