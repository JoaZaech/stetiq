import type { Element } from 'hast'
import ReactMarkdown, { type Components } from 'react-markdown'
import { Link } from 'react-router'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'
import rehypeHighlight from 'rehype-highlight'
import rehypeSlug from 'rehype-slug'
import remarkGfm from 'remark-gfm'
import { GuideDiagram } from './GuideDiagram'
import { guideLink } from './guide-index'
import './guide-highlight.css'

const components: Components = {
  a: ({ href = '', children }) => {
    const route = guideLink(href)
    if (route !== undefined) return <Link to={route}>{children}</Link>
    // Heading anchors and other in-page links stay on this page.
    if (href.startsWith('#')) return <a href={href}>{children}</a>
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    )
  },
  pre: ({ node, children }) => {
    const diagram = node && mermaidSource(node)
    if (diagram !== undefined) return <GuideDiagram source={diagram} />
    return <pre>{children}</pre>
  },
}

/** The source of a fenced `mermaid` block (`<pre><code class="language-mermaid">`). */
function mermaidSource(pre: Element): string | undefined {
  const [code] = pre.children
  if (code?.type !== 'element' || code.tagName !== 'code') return undefined
  const classes = code.properties.className
  if (!Array.isArray(classes) || !classes.includes('language-mermaid')) return undefined
  return code.children.map((child) => (child.type === 'text' ? child.value : '')).join('')
}

/**
 * Renders a user guide page (`docs/guide/`) as docs: GFM tables, headings with stable
 * anchors that link to themselves, highlighted code, and fenced `mermaid` blocks drawn as
 * diagrams (`GuideDiagram`). Links to other guide files navigate inside the app, other
 * links open in a new tab, and raw HTML is not rendered.
 *
 * Not for user-written text such as a Knowledge Graph description: that is `Markdown`.
 */
export function GuideMarkdown({ children }: { children: string }) {
  return (
    <div
      className={
        'prose prose-sm max-w-none dark:prose-invert ' +
        'prose-a:text-primary prose-a:underline-offset-2 ' +
        'prose-headings:scroll-mt-4 prose-headings:[&_a]:text-inherit prose-headings:[&_a]:no-underline ' +
        'prose-pre:border prose-pre:bg-muted prose-pre:text-foreground ' +
        'prose-code:before:content-none prose-code:after:content-none'
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          rehypeSlug,
          [rehypeAutolinkHeadings, { behavior: 'wrap' }],
          [rehypeHighlight, { plainText: ['mermaid'] }],
        ]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
