import { useId, type ReactNode } from 'react'
import { Label } from '@/components/ui/label'

export interface ControlProps {
  id: string
  value: string
  onChange: (event: { target: { value: string } }) => void
  'aria-invalid': boolean | undefined
  'aria-describedby': string | undefined
}

export interface FieldProps {
  label: string
  hint?: string
  value: string
  error: string | undefined
  onChange: (value: string) => void
  children: (props: ControlProps) => ReactNode
}

/** A labelled form control with its hint and, when invalid, its error message. */
export function Field({ label, hint, value, error, onChange, children }: FieldProps) {
  const id = useId()
  const described = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ')
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        value,
        onChange: (event) => onChange(event.target.value),
        'aria-invalid': error ? true : undefined,
        'aria-describedby': described || undefined,
      })}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
