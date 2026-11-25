import { useEffect, useState, useSyncExternalStore } from 'react'
import { useAuth } from '../../components/auth/AuthProvider'
import { useWorkspace } from '../../components/workspace/WorkspaceProvider'
import { apiRequest } from '../../lib/api'
import { SweepContext } from './SweepContext'
import { createApiSweepRepository } from './sweepApi'

export default function SweepProvider({ children }) {
  const { csrfToken, isAuthenticated } = useAuth()
  const workspace = useWorkspace()
  const [repository] = useState(() => createApiSweepRepository({ request: apiRequest }))
  useEffect(() => { repository.setCsrfToken(csrfToken) }, [csrfToken, repository])
  const snapshot = useSyncExternalStore(repository.subscribe, repository.getSnapshot)

  useEffect(() => {
    if (isAuthenticated) repository.refresh()
    else repository.reset()
  }, [isAuthenticated, repository])

  return <SweepContext.Provider value={{
    ...snapshot, repository,
    algorithms: workspace.scripts,
    datasets: workspace.datasets,
    // Sweep runs are ordinary experiments; keep the runs console in step.
    refreshExperiments: workspace.refreshExperiments,
  }}>{children}</SweepContext.Provider>
}
