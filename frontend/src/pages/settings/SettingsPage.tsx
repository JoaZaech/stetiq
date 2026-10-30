import { useId, type ReactNode } from 'react'
import { useWhoAmI, type WhoAmI } from '@/api/whoami'
import { ErrorAlert } from '@/components/ErrorAlert'
import { PageHeader } from '@/components/PageHeader'
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

// Server mode (signed in with an API Token) is shown by the sign-in ticket (#23).
function AccessDetails({ whoami }: { whoami: WhoAmI }) {
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
