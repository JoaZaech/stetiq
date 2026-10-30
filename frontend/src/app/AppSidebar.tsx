import { BookOpen, ExternalLink, Network, Settings } from 'lucide-react'
import { Link, useMatch } from 'react-router'
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

const DOCS_URL = 'https://github.com/JoaZaech/stetiq#readme'

/**
 * The left sidebar. Inside a Knowledge Graph it will expand into that graph's
 * sections (a later ticket); add those entries here, keyed off `useMatch('/kg/:name/*')`.
 */
export function AppSidebar() {
  const atSettings = useMatch('/settings') !== null
  const atLanding = useMatch('/') !== null
  const inKnowledgeGraph = useMatch('/kg/*') !== null
  const atKnowledgeGraphs = atLanding || inKnowledgeGraph

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
        <nav aria-label="Main">
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={atKnowledgeGraphs} tooltip="Knowledge Graphs">
                    <Link to="/">
                      <Network />
                      <span>Knowledge Graphs</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
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
