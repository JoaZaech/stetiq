import type { Element } from 'hast'
import { useMemo } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import { Link } from 'react-router'
import rehypeAutolinkHeadings from 'rehype-autolink-headings'
import rehypeHighlight from 'rehype-highlight'
import rehypeSlug from 'rehype-slug'
import remarkGfm from 'remark-gfm'
import { GuideDiagram } from './GuideDiagram'
import { guideLink } from './guide-index'
import './guide-highlight.css'

/** How a Help page whose source is `from` (a repository path) renders links and code blocks. */
function guideComponents(from: string): Components {
  return {
    a: ({ href = '', children }) => {
      const target = guideLink(href, from)
      if ('route' in target) return <Link to={target.route}>{children}</Link>
      // Heading anchors and other in-page links stay on this page.
      if (target.url.startsWith('#')) return <a href={target.url}>{children}</a>
      return (
        <a href={target.url} target="_blank" rel="noreferrer">
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
 * Renders a Help page (`docs/guide/`, `docs/vision.md`) as docs: GFM tables, headings with
 * stable anchors that link to themselves, highlighted code, and fenced `mermaid` blocks
 * drawn as diagrams (`GuideDiagram`). Links to other Help pages navigate inside the app;
 * links to other repository files, resolved from the page's source path `from`, open on
 * GitHub in a new tab, as do external links. Raw HTML is not rendered.
 *
 * Not for user-written text such as a Knowledge Graph description: that is `Markdown`.
 */
export function GuideMarkdown({ from, children }: { from: string; children: string }) {
  const components = useMemo(() => guideComponents(from), [from])
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
