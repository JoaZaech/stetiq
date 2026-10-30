import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { readStored, writeStored } from '@/lib/local-storage'
import { ThemeContext } from './theme-context'
import { parseTheme, resolveTheme, THEME_STORAGE_KEY, type Theme } from './theme'

const DARK_QUERY = '(prefers-color-scheme: dark)'

/** Applies the chosen theme to <html> and keeps it in localStorage. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => parseTheme(readStored(THEME_STORAGE_KEY)))
  const [systemDark, setSystemDark] = useState(() => matchMedia(DARK_QUERY).matches)

  useEffect(() => {
    const media = matchMedia(DARK_QUERY)
    const onChange = () => setSystemDark(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  const resolved = resolveTheme(theme, systemDark)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolved === 'dark')
  }, [resolved])

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    // Blocked storage (private mode): the choice lasts for this page only.
    writeStored(THEME_STORAGE_KEY, next)
  }, [])

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
