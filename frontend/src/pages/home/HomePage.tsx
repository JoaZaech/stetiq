import { Link } from 'react-router'
import { PageHeader } from '@/components/PageHeader'
import { helpUrl } from '@/pages/help/guide-index'
import { RecentKnowledgeGraphs } from './RecentKnowledgeGraphs'

/** The guide's first page (docs/guide/01-getting-started.md), where Home points newcomers. */
const FIRST_GUIDE_PAGE = 'getting-started'

/** `/`: where the app opens. */
export function HomePage() {
  return (
    <>
      <PageHeader
        title="Welcome to stetiq"
        tabTitle="Home"
        description={
          <>
            New to stetiq?{' '}
            <Link to={helpUrl(FIRST_GUIDE_PAGE)} className="font-medium text-primary underline-offset-4 hover:underline">
              Read the guide
            </Link>
          </>
        }
      />
      <RecentKnowledgeGraphs />
    </>
  )
}
