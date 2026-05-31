import { Compass } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { EmptyState } from '../components/EmptyState'

/**
 * Stub Explore screen — the real implementation lands with E9-S3 (history +
 * new tabs, backend endpoints, navigation back into the Feed via `?start=`).
 * Shipping a placeholder lets us wire the BottomNav tab now so the navigation
 * shape matches the final spec.
 */
export const ExplorePlaceholder = () => (
  <div className="flex flex-col h-dvh overflow-y-auto relative">
    <BlobBackground />

    <header
      className="relative z-10 flex items-center justify-center"
      style={{ padding: '16px 20px 8px' }}
    >
      <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
        Explore
      </h1>
    </header>

    <div className="relative z-10 flex-1 flex items-center justify-center">
      <EmptyState
        icon={Compass}
        title="Bientôt disponible"
        description="Historique et nouveautés arrivent avec E9-S3. En attendant, parcours ton feed depuis l'accueil."
      />
    </div>

    <BottomNav />
  </div>
)
