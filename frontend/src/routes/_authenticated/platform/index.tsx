import { createFileRoute } from '@tanstack/react-router'
import { PlatformAlphas } from '@/features/platform'

export const Route = createFileRoute('/_authenticated/platform/')({
  component: PlatformAlphas,
})
