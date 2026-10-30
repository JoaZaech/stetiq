/**
 * The one place the UI talks to the server. The UI is just another `/api/v1` client
 * (ADR 0003): every request goes through `api()` (or `send()` for the sign-in routes
 * outside `/api/v1`), so auth, CSRF and error handling live here and nowhere else.
 *
 * Resource modules next to this file (e.g. `whoami.ts`) hold the wire types, the
 * fetchers and their TanStack Query hooks for one area of the API.
 */

export const API_PREFIX = '/api/v1'
/** Where `api()` sends the browser when the server wants a token (server mode). */
export const SIGN_IN_PAGE = '/ui/sign-in'
/** The readable cookie the server sets at sign-in, echoed in this header on writes. */
const CSRF_COOKIE = 'stetiq_csrf'
const CSRF_HEADER = 'X-CSRF-Token'

/** A stetiq error from the server: `{"error": {"type", "message"}}` (wire.error_to_json). */
export class ApiError extends Error {
  readonly status: number
  /** The StetiqError subclass name, e.g. `NotFoundError`, `PermissionDeniedError`. */
  readonly type: string

  constructor(status: number, type: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.type = type
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/**
 * Call `API_PREFIX + path`; returns the parsed JSON body or throws `ApiError`.
 *
 * A 401 (nobody signed in, or the token was revoked) sends the browser to the
 * sign-in page, which brings the user back to this page afterwards.
 */
export async function api<T>(path: string, method: Method = 'GET', body?: unknown): Promise<T> {
  try {
    return await send<T>(API_PREFIX + path, method, body)
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) goToSignIn()
    throw error
  }
}

/** A same-origin request to `url`, with the CSRF header on writes; throws `ApiError`. */
export async function send<T>(url: string, method: Method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const csrf = readCookie(CSRF_COOKIE)
  if (method !== 'GET' && csrf) headers[CSRF_HEADER] = csrf
  const response = await fetch(url, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const payload: unknown = await response.json().catch(() => undefined)
  if (!response.ok) throw toApiError(response, payload)
  return payload as T
}

function toApiError(response: Response, payload: unknown): ApiError {
  const error = (payload as { error?: { type?: string; message?: string } } | undefined)?.error
  return new ApiError(
    response.status,
    error?.type ?? 'HttpError',
    error?.message ?? `${response.status} ${response.statusText}`,
  )
}

function readCookie(name: string): string | undefined {
  const prefix = `${name}=`
  const found = document.cookie.split('; ').find((c) => c.startsWith(prefix))
  return found === undefined ? undefined : decodeURIComponent(found.slice(prefix.length))
}

function goToSignIn() {
  const { pathname, search } = window.location
  if (pathname.startsWith(SIGN_IN_PAGE)) return
  const next = pathname.replace(/^\/ui/, '') + search
  window.location.assign(`${SIGN_IN_PAGE}?next=${encodeURIComponent(next || '/')}`)
}

/** `/knowledge-graphs/<name>`, like `_kg_path` in the Python remote service. */
export function kgPath(name: string): string {
  return `/knowledge-graphs/${encodeURIComponent(name)}`
}
