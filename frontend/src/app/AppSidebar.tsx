import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, House, Settings } from 'lucide-react'
import { Link, NavLink, useMatch } from 'react-router'
import { knowledgeGraphsQuery } from '@/api/knowledge-graphs'
import { Logo } from '@/components/Logo'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { readStored, writeStored } from '@/lib/local-storage'
import { KNOWLEDGE_GRAPH_SECTIONS, kgUrl, type KnowledgeGraphSection } from './knowledge-graph-sections'
import { KnowledgeGraphSwitcher } from './KnowledgeGraphSwitcher'

/** The Knowledge Graph last opened in this browser: outside one, the sections lead into it. */
const LAST_KNOWLEDGE_GRAPH_KEY = 'stetiq.last-knowledge-graph'

/**
 * The left sidebar: Home, the Knowledge Graph switcher, the sections of a Knowledge
 * Graph (from `KNOWLEDGE_GRAPH_SECTIONS`, so add a section there, not here), then Help
 * and Settings. The layout is the same on every page; only where the sections lead
 * changes: into the open Knowledge Graph, else the last one opened, else nowhere
 * (disabled). The last one opened is trusted until a loaded Knowledge Graph list lacks
 * it, so the items lead into it while the list loads, or on Help, where it is not loaded.
 *
 * On Help, which renders signed out, the sidebar asks for no session data (see
 * `AppLayout`): it uses a Knowledge Graph list already loaded, and loads one only when
 * the user opens the switcher.
 */
export function AppSidebar() {
  const atHome = useMatch('/') !== null
  const atSettings = useMatch('/settings') !== null
  const atHelp = useMatch('/help/*') !== null
  const current = useMatch('/kg/:name/*')?.params.name
  const openSection = useMatch('/kg/:name/:section/*')?.params.section
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const knowledgeGraphs = useQuery({ ...knowledgeGraphsQuery, enabled: !atHelp || switcherOpen })

  useEffect(() => {
    if (current !== undefined) writeStored(LAST_KNOWLEDGE_GRAPH_KEY, current)
  }, [current])

  const remembered = readStored(LAST_KNOWLEDGE_GRAPH_KEY) ?? undefined
  const rememberedIsGone =
    knowledgeGraphs.data !== undefined && !knowledgeGraphs.data.some((kg) => kg.name === remembered)
  const target = current ?? (rememberedIsGone ? undefined : remembered)

  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="stetiq">
              <Link to="/">
                <Logo className="size-6! shrink-0 text-primary" />
                <span className="flex items-baseline gap-2">
                  <span className="text-base font-semibold">stetiq</span>
                  <span className="text-xs text-muted-foreground">v{__STETIQ_VERSION__}</span>
                </span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Main" className="flex flex-1 flex-col">
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu className="gap-1">
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={atHome} tooltip="Home">
                    <Link to="/">
                      <House />
                      <span>Home</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <KnowledgeGraphSwitcher
                  current={current}
                  knowledgeGraphs={knowledgeGraphs}
                  open={switcherOpen}
                  onOpenChange={setSwitcherOpen}
                />
                {KNOWLEDGE_GRAPH_SECTIONS.map((section) => (
                  <SectionItem
                    key={section.path}
                    section={section}
                    knowledgeGraph={target}
                    isActive={current !== undefined && openSection === section.path}
                  />
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
          <SidebarGroup className="mt-auto">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={atHelp} tooltip="Help">
                    <Link to="/help">
                      <BookOpen />
                      <span>Help</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={atSettings} tooltip="Settings">
                    <Link to="/settings">
                      <Settings />
                      <span>Settings</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </nav>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  )
}

interface SectionItemProps {
  section: KnowledgeGraphSection
  /** The Knowledge Graph the item leads into; undefined: disabled, saying why. */
  knowledgeGraph: string | undefined
  isActive: boolean
}

/** A section's sidebar item. Disabled, it keeps its place, so the sidebar never shifts. */
function SectionItem({ section: { path, label, icon: Icon }, knowledgeGraph, isActive }: SectionItemProps) {
  if (knowledgeGraph === undefined) {
    return (
      <SidebarMenuItem>
        <Tooltip>
          <TooltipTrigger asChild>
            <SidebarMenuButton asChild className="cursor-not-allowed aria-disabled:pointer-events-auto">
              {/* No href, so the link role is spelled out; it still takes focus for the tooltip. */}
              <a role="link" aria-disabled="true" tabIndex={0}>
                <Icon />
                <span>{label}</span>
              </a>
            </SidebarMenuButton>
          </TooltipTrigger>
          <TooltipContent side="right">Select a Knowledge Graph first</TooltipContent>
        </Tooltip>
      </SidebarMenuItem>
    )
  }
  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={isActive} tooltip={label}>
        <NavLink to={kgUrl(knowledgeGraph, path)}>
          <Icon />
          <span>{label}</span>
        </NavLink>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}
