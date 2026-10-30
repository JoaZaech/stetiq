import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LogOut } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { signOut } from '@/api/session'
import { ALL_KNOWLEDGE_GRAPHS, useWhoAmI, type WhoAmI } from '@/api/whoami'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Skeleton } from '@/components/ui/skeleton'
import { useTheme } from '@/theme/theme-context'
import { THEMES, type Theme } from '@/theme/theme'

const THEME_LABELS: Record<Theme, string> = { system: 'System', light: 'Light', dark: 'Dark' }

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" />
      <div className="max-w-2xl space-y-8">
        <Section title="Appearance">
          <ThemeChoice />
        </Section>
        <Section title="Access">
          <Access />
        </Section>
      </div>
    </>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h2 id={id} className="text-sm font-semibold">
        {title}
      </h2>
      {children}
    </section>
  )
}

function ThemeChoice() {
  const { theme, setTheme } = useTheme()
  const id = useId()
  return (
    <RadioGroup
      aria-label="Theme"
      value={theme}
      onValueChange={(value) => setTheme(value as Theme)}
      className="flex gap-6"
    >
      {THEMES.map((t) => (
        <div key={t} className="flex items-center gap-2">
          <RadioGroupItem value={t} id={`${id}-${t}`} />
          <Label htmlFor={`${id}-${t}`}>{THEME_LABELS[t]}</Label>
        </div>
      ))}
    </RadioGroup>
  )
}

function Access() {
  const whoami = useWhoAmI()
  if (whoami.isPending) return <Skeleton className="h-10 w-80" />
  if (whoami.isError) return <ErrorAlert error={whoami.error} title="Could not load your access" />
  return <AccessDetails whoami={whoami.data} />
}

function AccessDetails({ whoami }: { whoami: WhoAmI }) {
  if (whoami.mode === 'server') return <SignedIn whoami={whoami} />
  return (
    <div className="space-y-1 text-sm">
      <p className="font-medium">Local mode</p>
      <p className="text-muted-foreground">
        Running <code className="font-mono">stetiq ui</code> without a token: every Knowledge
        Graph is editable, and changes are recorded as{' '}
        <span className="font-medium text-foreground">{whoami.user}</span>.
      </p>
    </div>
  )
}

function SignedIn({ whoami }: { whoami: WhoAmI }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const signingOut = useMutation({
    mutationFn: signOut,
    onSuccess: () => {
      queryClient.clear()
      void navigate('/sign-in', { replace: true })
    },
  })
  const grants = Object.entries(whoami.grants).sort(([a], [b]) => grantOrder(a, b))

  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p>
          Signed in as <span className="font-medium">{whoami.user}</span>
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => signingOut.mutate()}
          disabled={signingOut.isPending}
        >
          <LogOut />
          Sign out
        </Button>
      </div>
      {signingOut.isError && <ErrorAlert error={signingOut.error} title="Could not sign out" />}
      <table aria-label="Grants" className="w-full border-collapse">
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b">
            <th className="py-2 pr-4 font-medium">Knowledge Graph</th>
            <th className="py-2 font-medium">Permission</th>
          </tr>
        </thead>
        <tbody>
          {grants.map(([kg, permission]) => (
            <tr key={kg} className="border-b last:border-0">
              <td className="py-2 pr-4">
                {kg === ALL_KNOWLEDGE_GRAPHS ? 'All Knowledge Graphs' : kg}
              </td>
              <td className="py-2">
                <Badge variant={permission === 'edit' ? 'default' : 'secondary'}>{permission}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** `*` first, then by name. */
function grantOrder(a: string, b: string): number {
  if (a === ALL_KNOWLEDGE_GRAPHS || b === ALL_KNOWLEDGE_GRAPHS) {
    return a === ALL_KNOWLEDGE_GRAPHS ? -1 : 1
  }
  return a.localeCompare(b)
}
