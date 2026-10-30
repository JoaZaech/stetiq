import { useId } from 'react'
import { Star } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

/** One chip per Alias pointing to a version; the Contract Alias is highlighted. */
export function AliasChips({ aliases, contractAlias }: { aliases: string[]; contractAlias?: string }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {aliases.map((alias) =>
        alias === contractAlias ? (
          <ContractAliasChip key={alias} alias={alias} />
        ) : (
          <Badge key={alias} variant="secondary">
            {alias}
          </Badge>
        ),
      )}
    </span>
  )
}

function ContractAliasChip({ alias }: { alias: string }) {
  const id = useId()
  return (
    <Badge aria-describedby={id}>
      <Star aria-hidden />
      {alias}
      <span id={id} hidden>
        Contract Alias
      </span>
    </Badge>
  )
}

export function CandidateBadge() {
  return (
    <Badge variant="outline" className="border-dashed">
      Candidate
    </Badge>
  )
}
