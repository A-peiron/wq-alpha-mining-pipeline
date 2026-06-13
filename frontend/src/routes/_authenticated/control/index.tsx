import { createFileRoute } from '@tanstack/react-router'
import { ControlCenter } from '@/features/control'

export const Route = createFileRoute('/_authenticated/control/')({
  component: ControlCenter,
})
