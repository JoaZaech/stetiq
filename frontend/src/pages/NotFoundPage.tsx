import { Link } from 'react-router'
import { PageHeader } from '@/components/PageHeader'

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" />
      <p className="text-sm">
        There is no page at this address.{' '}
        <Link to="/" className="text-primary underline-offset-4 hover:underline">
          Back to Knowledge Graphs
        </Link>
      </p>
    </>
  )
}
