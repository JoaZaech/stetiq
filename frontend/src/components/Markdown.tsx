import ReactMarkdown from 'react-markdown'
import { cn } from '@/lib/utils'

/**
 * Renders user-written markdown (e.g. a Knowledge Graph description). Raw HTML in the
 * source is not rendered, and links open in a new tab.
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div
      className={cn(
        'space-y-2 text-sm break-words',
        '[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2',
        '[&_ul]:list-disc [&_ol]:list-decimal [&_ul,&_ol]:space-y-0.5 [&_ul,&_ol]:pl-5',
        '[&_h1,&_h2,&_h3,&_h4]:font-semibold [&_h1]:text-base [&_h2]:text-base',
        '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs',
        '[&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3',
        '[&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground',
        className,
      )}
    >
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
