import { ArrowLeft, BookOpen, ExternalLink, Network, Settings } from 'lucide-react'
import { Link, NavLink, useMatch } from 'react-router'
import { Logo } from '@/components/Logo'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { KNOWLEDGE_GRAPH_SECTIONS, kgUrl } from './knowledge-graph-sections'

const DOCS_URL = 'https://github.com/JoaZaech/stetiq#readme'

/**
 * The left sidebar. Inside a Knowledge Graph (`/kg/:name/*`) the Knowledge Graphs entry
 * becomes a back control and the graph's sections appear under its name; the sections
 * come from `KNOWLEDGE_GRAPH_SECTIONS`, so add a section there, not here.
 */
export function AppSidebar() {
  const atSettings = useMatch('/settings') !== null
  const atLanding = useMatch('/') !== null
  const knowledgeGraph = useMatch('/kg/:name/*')?.params.name

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
              <SidebarMenu>
                <SidebarMenuItem>
                  {knowledgeGraph === undefined ? (
                    <SidebarMenuButton asChild isActive={atLanding} tooltip="Knowledge Graphs">
                      <Link to="/">
                        <Network />
                        <span>Knowledge Graphs</span>
                      </Link>
                    </SidebarMenuButton>
                  ) : (
                    <SidebarMenuButton asChild tooltip="Back to Knowledge Graphs">
                      <Link to="/" aria-label="Back to Knowledge Graphs">
                        <ArrowLeft />
                        <span>Knowledge Graphs</span>
                      </Link>
                    </SidebarMenuButton>
                  )}
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
          {knowledgeGraph !== undefined && <KnowledgeGraphNav name={knowledgeGraph} />}
          <SidebarGroup className="mt-auto">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild tooltip="Docs">
                    <a href={DOCS_URL} target="_blank" rel="noreferrer">
                      <BookOpen />
                      <span>Docs</span>
                      <ExternalLink className="ml-auto size-3! text-muted-foreground" aria-hidden />
                    </a>
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

/** The sections of the open Knowledge Graph, under its name. */
function KnowledgeGraphNav({ name }: { name: string }) {
  const section = useMatch('/kg/:name/:section/*')?.params.section
  return (
    <nav aria-label="Knowledge Graph">
      <SidebarGroup>
        <SidebarGroupLabel className="truncate">{name}</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            {KNOWLEDGE_GRAPH_SECTIONS.map(({ path, label, icon: Icon }) => (
              <SidebarMenuItem key={path}>
                <SidebarMenuButton asChild isActive={section === path} tooltip={label}>
                  <NavLink to={kgUrl(name, path)}>
                    <Icon />
                    <span>{label}</span>
                  </NavLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </nav>
  )
}
