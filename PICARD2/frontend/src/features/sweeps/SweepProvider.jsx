import { useEffect, useState, useSyncExternalStore } from 'react'
import { useWorkspace } from '../../components/workspace/WorkspaceProvider'
import { SWEEPS_DEMO_MODE } from './config'
import { demoAlgorithms, demoDatasets } from './demoCatalog'
import { SweepContext } from './SweepContext'
import { createDemoSweepRepository, SWEEP_STORAGE_KEY, unconnectedSweepRepository } from './sweepRepository'

export default function SweepProvider({ children }) {
  const workspace = useWorkspace()
  const [repository] = useState(() => SWEEPS_DEMO_MODE ? createDemoSweepRepository({
    // Accessing localStorage itself can throw in privacy-restricted browsers.
    storage: { getItem: (key) => window.localStorage.getItem(key), setItem: (key, value) => window.localStorage.setItem(key, value) },
    withLock: (action) => navigator.locks ? navigator.locks.request(SWEEP_STORAGE_KEY, action) : action(),
  }) : unconnectedSweepRepository)
  const snapshot = useSyncExternalStore(repository.subscribe, repository.getSnapshot)
  useEffect(() => {
    repository.refresh()
    if (!SWEEPS_DEMO_MODE) return
    const interval = window.setInterval(() => repository.tick().catch(() => {}), 1000)
    const onStorage = (event) => { if (event.key === SWEEP_STORAGE_KEY || event.key === null) repository.refresh() }
    window.addEventListener('storage', onStorage)
    return () => { window.clearInterval(interval); window.removeEventListener('storage', onStorage) }
  }, [repository])
  return <SweepContext.Provider value={{
    ...snapshot, repository, isDemo: SWEEPS_DEMO_MODE,
    algorithms: SWEEPS_DEMO_MODE ? demoAlgorithms : workspace.scripts,
    datasets: SWEEPS_DEMO_MODE ? demoDatasets : workspace.datasets,
  }}>{children}</SweepContext.Provider>
}
