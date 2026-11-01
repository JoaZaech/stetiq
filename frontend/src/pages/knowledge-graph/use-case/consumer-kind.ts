import { AppWindow, Bot, Box, LayoutDashboard, Users } from 'lucide-react'

/** The kinds GLOSSARY.md names for a Consumer, each with its own icon, and `other`. */
export const CONSUMER_KIND_ICONS = {
  application: AppWindow,
  agent: Bot,
  dashboard: LayoutDashboard,
  team: Users,
  other: Box,
} as const

export type ConsumerKindIcon = keyof typeof CONSUMER_KIND_ICONS

/**
 * Which icon a Consumer's `kind` gets. The kind is free text, so a known one matches
 * whatever its case or surrounding spaces, and any other kind, or none, is `other`.
 */
export function consumerKindIcon(kind: string | undefined): ConsumerKindIcon {
  const known = kind?.trim().toLowerCase()
  return known && Object.hasOwn(CONSUMER_KIND_ICONS, known) ? (known as ConsumerKindIcon) : 'other'
}
