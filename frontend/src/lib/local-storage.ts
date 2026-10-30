/**
 * `localStorage`, for per-browser conveniences only. Storage can be blocked or cleared,
 * so a failed read is `null` (nothing stored) and a failed write is dropped.
 */
export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Blocked storage: the setting just isn't remembered.
  }
}
