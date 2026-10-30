import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useId, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { afterSignIn, signIn } from '@/api/session'
import { whoAmIQuery } from '@/api/whoami'
import { ErrorAlert } from '@/components/ErrorAlert'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { helpUrl } from '@/pages/help/guide-index'

/** The guide page (docs/guide/05-server-and-api-tokens.md) on getting an API Token. */
const SERVER_GUIDE_PAGE = 'server-and-api-tokens'

/**
 * Server mode: paste an existing API Token (ADR 0002: the UI never issues one). The
 * server keeps it in an HttpOnly cookie, then we go back to the page that asked.
 */
export function SignInPage() {
  const [token, setToken] = useState('')
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const tokenId = useId()

  useEffect(() => {
    document.title = 'Sign in · stetiq'
  }, [])

  const signingIn = useMutation({
    mutationFn: signIn,
    onSuccess: (whoami) => {
      // Nothing cached under the previous identity may leak into this one.
      queryClient.clear()
      queryClient.setQueryData(whoAmIQuery.queryKey, whoami)
      void navigate(afterSignIn(params.get('next')), { replace: true })
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    signingIn.mutate(token.trim())
  }

  return (
    <main className="flex min-h-svh items-center justify-center bg-sidebar p-4">
      <div className="w-full max-w-sm space-y-6 rounded-xl border bg-background p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <Logo className="size-6 text-primary" />
          <span className="text-base font-semibold">stetiq</span>
        </div>
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
          <p className="text-sm text-muted-foreground">
            Paste an API Token. An administrator issues one with{' '}
            <code className="font-mono">stetiq token create</code>. See{' '}
            <Link to={helpUrl(SERVER_GUIDE_PAGE)} className="font-medium underline underline-offset-4">
              Server &amp; API Tokens
            </Link>{' '}
            in Help.
          </p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={tokenId}>API Token</Label>
            <Input
              id={tokenId}
              type="password"
              autoComplete="off"
              spellCheck={false}
              required
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="font-mono"
            />
          </div>
          {signingIn.isError && (
            <ErrorAlert error={signingIn.error} title="Could not sign in" />
          )}
          <Button type="submit" className="w-full" disabled={signingIn.isPending}>
            Sign in
          </Button>
        </form>
      </div>
    </main>
  )
}
