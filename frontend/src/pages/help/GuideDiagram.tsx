import { useEffect, useState, useSyncExternalStore } from 'react'

type Drawing = { svg: string } | { error: string }

/**
 * A fenced `mermaid` block of a guide page, drawn as a diagram in the app's light or dark
 * colours and redrawn when the theme changes. Mermaid is only downloaded once a page has a
 * diagram. A diagram that does not parse shows its source and the reason instead.
 */
export function GuideDiagram({ source }: { source: string }) {
  const dark = useDarkTheme()
  const [drawing, setDrawing] = useState<Drawing>()

  useEffect(() => {
    let current = true
    drawDiagram(source, dark).then(
      (svg) => current && setDrawing({ svg }),
      (error: unknown) => current && setDrawing({ error: firstLine(error) }),
    )
    return () => {
      current = false
    }
  }, [source, dark])

  return (
    <figure className="not-prose my-6">
      {drawing && 'svg' in drawing && (
        // Mermaid's strict security level sanitises the SVG it returns.
        <div className="flex justify-center" dangerouslySetInnerHTML={{ __html: drawing.svg }} />
      )}
      {drawing && 'error' in drawing && (
        <>
          <pre className="overflow-x-auto rounded-md border bg-muted p-3 text-xs">
            <code>{source}</code>
          </pre>
          <figcaption className="mt-2 text-xs text-destructive">
            This diagram couldn't be drawn: {drawing.error}
          </figcaption>
        </>
      )}
    </figure>
  )
}

let diagrams = 0
let queue: Promise<unknown> = Promise.resolve()

/**
 * Renders one diagram to SVG. Mermaid's configuration is global, so drawings take turns:
 * each sets its own theme right before rendering.
 */
function drawDiagram(source: string, dark: boolean): Promise<string> {
  const drawing = queue.then(async () => {
    const { default: mermaid } = await import('mermaid')
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      suppressErrorRendering: true,
      theme: dark ? 'dark' : 'default',
    })
    const { svg } = await mermaid.render(`guide-diagram-${++diagrams}`, source)
    return svg
  })
  queue = drawing.catch(() => undefined)
  return drawing
}

function firstLine(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  return message.split('\n')[0]
}

/** Whether the app is in dark mode: the `.dark` class ThemeProvider sets on <html>. */
function useDarkTheme(): boolean {
  return useSyncExternalStore(subscribeToTheme, () =>
    document.documentElement.classList.contains('dark'),
  )
}

function subscribeToTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  return () => observer.disconnect()
}
