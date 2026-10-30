import { Link } from 'react-router'
import { PageHeader } from '@/components/PageHeader'

interface NotFoundPageProps {
  title?: string
  message?: string
}

/** Unknown addresses, and ids the user cannot read (shown exactly like unknown ones). */
export function NotFoundPage({
  title = 'Page not found',
  message = 'There is no page at this address.',
}: NotFoundPageProps) {
  return (
    <>
      <PageHeader title={title} />
      <p className="text-sm">
        {message}{' '}
        <Link to="/kg" className="text-primary underline-offset-4 hover:underline">
          Back to Knowledge Graphs
        </Link>
      </p>
    </>
  )
}
