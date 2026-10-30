import { useId, useState } from 'react'
import { ArrowUpRight, TriangleAlert } from 'lucide-react'
import { type Alias, useAliases, useContractAlias, usePromote } from '@/api/aliases'
import { ErrorAlert } from '@/components/ErrorAlert'
import { OntologyDiffPanel } from '@/components/OntologyDiff'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Skeleton } from '@/components/ui/skeleton'
import { LatestGateResult } from './LatestGateResult'

/** The radio value for "type a new Alias name"; real Alias names can't contain a space. */
const NEW_ALIAS = 'new alias'

interface PromoteDialogProps {
  name: string
  /** The Ontology Version being promoted. */
  number: number
  disabled: boolean
}

/**
 * The version page's Promote action: pick an Alias (or name a new one), see the
 * Ontology Diff against the version it points to now and this version's latest Gate
 * result, then move it. The Contract Alias needs an extra confirmation.
 */
export function PromoteDialog({ name, number, disabled }: PromoteDialogProps) {
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState('')
  const [newAlias, setNewAlias] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const aliases = useAliases(name)
  const contractAlias = useContractAlias(name)
  const promote = usePromote(name)

  const onOpenChange = (next: boolean) => {
    if (next) {
      setChoice('')
      setNewAlias('')
      setConfirmed(false)
      promote.reset()
    }
    setOpen(next)
  }
  const choose = (value: string) => {
    setChoice(value)
    setConfirmed(false)
  }

  const alias = choice === NEW_ALIAS ? newAlias.trim() : choice
  const current = aliases.data?.find((a) => a.name === alias)
  const isContract = alias !== '' && alias === contractAlias.data
  const unchanged = current?.version === number
  const ready = alias !== '' && !unchanged && (!isContract || confirmed) && !promote.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" disabled={disabled}>
          <ArrowUpRight />
          Promote
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault()
            if (!ready) return
            promote.mutate({ alias, version: number }, { onSuccess: () => setOpen(false) })
          }}
        >
          <DialogHeader>
            <DialogTitle>Promote v{number}</DialogTitle>
            <DialogDescription>
              Point an Alias at v{number}. The Promotion is recorded with you as the actor and
              v{number}'s latest Gate result.
            </DialogDescription>
          </DialogHeader>

          {aliases.isError && <ErrorAlert error={aliases.error} />}
          {aliases.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <AliasPicker
              aliases={aliases.data ?? []}
              contractAlias={contractAlias.data}
              choice={choice}
              onChoose={choose}
              newAlias={newAlias}
              onNewAliasChange={(value) => {
                setNewAlias(value)
                choose(NEW_ALIAS)
              }}
            />
          )}

          <section aria-label="Latest Gate result" className="grid gap-1.5">
            <h3 className="text-sm font-medium">Latest Gate result</h3>
            <LatestGateResult name={name} number={number} />
            <p className="text-xs text-muted-foreground">
              Gates never block a Promotion; the audit records this result.
            </p>
          </section>

          {alias !== '' &&
            (current === undefined ? (
              <p className="text-sm text-muted-foreground">
                {alias} does not exist yet: promoting creates it, pointing at v{number}.
              </p>
            ) : unchanged ? (
              <p className="text-sm text-muted-foreground">
                {alias} already points to v{number}.
              </p>
            ) : (
              <OntologyDiffPanel
                knowledgeGraph={name}
                base={current.version}
                target={number}
                caption={`Changes from v${current.version} (${alias}) to v${number}`}
              />
            ))}

          {isContract && !unchanged && (
            <ContractAliasConfirmation
              alias={alias}
              number={number}
              confirmed={confirmed}
              onConfirmedChange={setConfirmed}
            />
          )}

          {promote.isError && <ErrorAlert error={promote.error} title="Could not promote" />}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={!ready}>
              {promote.isPending ? 'Promoting…' : alias ? `Promote to ${alias}` : 'Promote'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface AliasPickerProps {
  aliases: readonly Alias[]
  contractAlias?: string
  choice: string
  onChoose: (value: string) => void
  newAlias: string
  onNewAliasChange: (value: string) => void
}

function AliasPicker({
  aliases,
  contractAlias,
  choice,
  onChoose,
  newAlias,
  onNewAliasChange,
}: AliasPickerProps) {
  const id = useId()
  const sorted = [...aliases].sort((a, b) => a.name.localeCompare(b.name))
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-sm font-medium">Alias</legend>
      <RadioGroup aria-label="Alias" value={choice} onValueChange={onChoose}>
        {sorted.map((alias) => (
          <div key={alias.name} className="flex items-center gap-2">
            <RadioGroupItem id={`${id}-${alias.name}`} value={alias.name} />
            <Label htmlFor={`${id}-${alias.name}`} className="font-normal">
              <span className="font-medium">{alias.name}</span>
              <span className="text-muted-foreground">v{alias.version}</span>
              {alias.name === contractAlias && <Badge variant="secondary">Contract Alias</Badge>}
            </Label>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <RadioGroupItem id={`${id}-new`} value={NEW_ALIAS} />
          <Label htmlFor={`${id}-new`} className="font-normal">
            New Alias
          </Label>
          <Input
            aria-label="New Alias name"
            className="h-8 max-w-56"
            placeholder="e.g. canary"
            value={newAlias}
            onChange={(event) => onNewAliasChange(event.target.value)}
            onFocus={() => onChoose(NEW_ALIAS)}
          />
        </div>
      </RadioGroup>
    </fieldset>
  )
}

interface ContractAliasConfirmationProps {
  alias: string
  number: number
  confirmed: boolean
  onConfirmedChange: (confirmed: boolean) => void
}

function ContractAliasConfirmation({
  alias,
  number,
  confirmed,
  onConfirmedChange,
}: ContractAliasConfirmationProps) {
  const id = useId()
  return (
    <Alert>
      <TriangleAlert aria-hidden />
      <AlertTitle>{alias} is the Contract Alias</AlertTitle>
      <AlertDescription className="grid gap-3">
        <p>
          New Construction Runs will declare v{number}, and Drift will be measured against
          v{number}.
        </p>
        <div className="flex items-center gap-2">
          <Checkbox
            id={id}
            checked={confirmed}
            onCheckedChange={(checked) => onConfirmedChange(checked === true)}
          />
          <Label htmlFor={id} className="font-normal text-foreground">
            Switch Construction Runs and Drift to v{number}
          </Label>
        </div>
      </AlertDescription>
    </Alert>
  )
}
