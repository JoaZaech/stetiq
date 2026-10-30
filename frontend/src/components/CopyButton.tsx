import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** One-click copy of an id or content hash, for pasting into the CLI or SDK. */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <Button variant="ghost" size="icon-xs" aria-label={label} title={label} onClick={() => void copy()}>
      {copied ? <Check /> : <Copy />}
    </Button>
  )
}
