/**
 * The one place the UI talks to the server. The UI is just another `/api/v1` client
 * (ADR 0003): every request goes through `api()`, so auth, CSRF and error handling
 * live here and nowhere else.
 *
 * Resource modules next to this file (e.g. `whoami.ts`) hold the wire types, the
 * fetchers and their TanStack Query hooks for one area of the API.
 */

export const API_PREFIX = '/api/v1'

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

/**
 * True for an id the user cannot see: unknown (404), or a Knowledge Graph outside the
 * token's grants (403). Pages show both as "not found", so ids reveal nothing.
 */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 403)
}

type Method ='GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/** Call `API_PREFIX + path`; returns the parsed JSON body or throws `ApiError`. */
export async function api<T>(path: string, method: Method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch(API_PREFIX + path, {
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

/** `/knowledge-graphs/<name>`, like `_kg_path` in the Python remote service. */
export function kgPath(name: string): string {
  return `/knowledge-graphs/${encodeURIComponent(name)}`
}
