import { PageHeader } from '@/components/PageHeader'
import { GettingStarted } from './GettingStarted'

/** `/`: where the app opens. */
export function HomePage() {
  return (
    <>
      <PageHeader title="Welcome to stetiq" tabTitle="Home" />
      <div className="space-y-8">
        <GettingStarted />
      </div>
    </>
  )
}
