/** The colour theme a viewer picks in Settings, kept in browser storage. */
export type Theme = 'system' | 'light' | 'dark'

export const THEMES: readonly Theme[] = ['system', 'light', 'dark']

/** The localStorage key; index.html reads it too, to avoid a flash of the wrong theme. */
export const THEME_STORAGE_KEY = 'stetiq.theme'

export function parseTheme(stored: string | null): Theme {
  return THEMES.find((t) => t === stored) ?? 'system'
}

export function resolveTheme(theme: Theme, systemPrefersDark: boolean): 'light' | 'dark' {
  if (theme === 'system') return systemPrefersDark ? 'dark' : 'light'
  return theme
}
