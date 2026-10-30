import { ChevronsUpDown, List, Network } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'
import type { UseQueryResult } from '@tanstack/react-query'
import type { KnowledgeGraphSummary } from '@/api/knowledge-graphs'
import {
  Command,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { kgListUrl, switchKnowledgeGraphUrl } from './knowledge-graph-sections'

const NONE_SELECTED = 'Select a Knowledge Graph'
const ALL_KNOWLEDGE_GRAPHS = 'All Knowledge Graphs'

interface KnowledgeGraphSwitcherProps {
  /** The open Knowledge Graph, if any. */
  current: string | undefined
  /** The readable Knowledge Graphs (a `knowledgeGraphsQuery` result), loaded or not. */
  knowledgeGraphs: UseQueryResult<KnowledgeGraphSummary[]>
  /** Whether the list is open: the caller holds it, so it can load the list on demand. */
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * The sidebar's Knowledge Graph context: a button naming the open Knowledge Graph that
 * opens a searchable list of all of them. Picking one keeps the open section
 * (`switchKnowledgeGraphUrl`); "All Knowledge Graphs" opens the list page.
 */
export function KnowledgeGraphSwitcher({ current, knowledgeGraphs, open, onOpenChange }: KnowledgeGraphSwitcherProps) {
  const navigate = useNavigate()
  const { pathname, search } = useLocation()

  function go(to: string) {
    onOpenChange(false)
    void navigate(to)
  }

  return (
    <SidebarMenuItem>
      <Popover open={open} onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>
          <SidebarMenuButton
            variant="outline"
            tooltip={current ?? NONE_SELECTED}
            aria-label={current === undefined ? undefined : `Knowledge Graph: ${current}`}
            className="data-open:bg-sidebar-accent"
          >
            <Network />
            <span className="flex-1 truncate">{current ?? NONE_SELECTED}</span>
            <ChevronsUpDown className="ml-auto text-muted-foreground" />
          </SidebarMenuButton>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-(--radix-popover-trigger-width) min-w-56 p-0">
          <Command label="Search Knowledge Graphs">
            <CommandInput placeholder="Search Knowledge Graphs" />
            <CommandList label="Knowledge Graphs">
              {knowledgeGraphs.data === undefined ? (
                <p className="px-2 py-3 text-center text-sm text-muted-foreground">
                  {knowledgeGraphs.isError ? 'Could not load the Knowledge Graphs' : 'Loading Knowledge Graphs…'}
                </p>
              ) : (
                <CommandGroup>
                  {knowledgeGraphs.data.map(({ name }) => (
                    <CommandItem
                      key={name}
                      value={name}
                      data-checked={name === current}
                      aria-checked={name === current}
                      onSelect={() => go(switchKnowledgeGraphUrl(pathname + search, name))}
                    >
                      <span className="truncate">{name}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
              <CommandSeparator alwaysRender />
              <CommandGroup forceMount>
                <CommandItem value={ALL_KNOWLEDGE_GRAPHS} forceMount onSelect={() => go(kgListUrl)}>
                  <List />
                  {ALL_KNOWLEDGE_GRAPHS}
                </CommandItem>
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </SidebarMenuItem>
  )
}
