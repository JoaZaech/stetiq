import type { SVGProps } from 'react'

/**
 * The stetiq mark: a small network graph of five nodes. Drawn in `currentColor`, so it
 * follows the text colour. public/favicon.svg is the same drawing.
 */
export function Logo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" role="img" aria-label="stetiq" {...props}>
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <line x1="5" y1="6" x2="12" y2="12.5" />
        <line x1="18" y1="4.5" x2="12" y2="12.5" />
        <line x1="12" y1="12.5" x2="5.5" y2="19" />
        <line x1="12" y1="12.5" x2="19" y2="17.5" />
        <line x1="18" y1="4.5" x2="19" y2="17.5" />
        <line x1="5" y1="6" x2="5.5" y2="19" />
      </g>
      <g fill="currentColor">
        <circle cx="5" cy="6" r="2.4" />
        <circle cx="18" cy="4.5" r="2.4" />
        <circle cx="12" cy="12.5" r="2.9" />
        <circle cx="5.5" cy="19" r="2.4" />
        <circle cx="19" cy="17.5" r="2.4" />
      </g>
    </svg>
  )
}
