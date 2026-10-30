import { send } from './client'
import type { WhoAmI } from './whoami'

/**
 * POST /auth/sign-in: the server checks the pasted API Token and keeps it in an
 * HttpOnly cookie, so page scripts never see it again. Throws `ApiError` (401) for an
 * invalid or revoked token.
 */
export function signIn(token: string): Promise<WhoAmI> {
  return send<WhoAmI>('/auth/sign-in', 'POST', { token })
}

/** POST /auth/sign-out: the browser forgets the token (the token itself stays valid). */
export function signOut(): Promise<void> {
  return send<void>('/auth/sign-out', 'POST')
}

/**
 * The app path to open after signing in: the `next` the user was sent from, if it is
 * a path inside the app, otherwise the Knowledge Graph list.
 */
export function afterSignIn(next: string | null): string {
  const inApp = next !== null && next.startsWith('/') && !/^\/[/\\]/.test(next)
  return inApp ? next : '/'
}
