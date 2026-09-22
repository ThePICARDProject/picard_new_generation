import { createContext, startTransition, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest, buildApiUrl } from '../../lib/api'
import { useAuth } from '../auth/AuthProvider'

const WorkspaceContext = createContext(null)
const ACTIVE_STATUSES = new Set(['Pending', 'Queued', 'Running'])

export function WorkspaceProvider({ children }) {
  const { csrfToken, isAuthenticated, isLoading: authLoading, user } = useAuth()
  const [datasets, setDatasets] = useState([])
  const [scripts, setScripts] = useState([])
  const [experiments, setExperiments] = useState([])
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [workspaceError, setWorkspaceError] = useState('')

  async function refreshDatasets() {
    const datasetData = await apiRequest('/datasets/')
    startTransition(() => {
      setDatasets(datasetData)
    })
    return datasetData
  }

  async function refreshScripts() {
    const scriptData = await apiRequest('/scripts/')
    startTransition(() => {
      setScripts(scriptData)
    })
    return scriptData
  }

  async function refreshExperiments() {
    const experimentData = await apiRequest('/experiments/')
    startTransition(() => {
      setExperiments(experimentData)
    })
    return experimentData
  }

  async function refreshAll() {
    if (!isAuthenticated) {
      return { datasets: [], scripts: [], experiments: [] }
    }

    setIsRefreshing(true)
    setWorkspaceError('')

    try {
      const [datasetData, scriptData, experimentData] = await Promise.all([
        apiRequest('/datasets/'),
        apiRequest('/scripts/'),
        apiRequest('/experiments/'),
      ])

      startTransition(() => {
        setDatasets(datasetData)
        setScripts(scriptData)
        setExperiments(experimentData)
      })

      return {
        datasets: datasetData,
        scripts: scriptData,
        experiments: experimentData,
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh workspace data.'
      setWorkspaceError(message)
      throw error
    } finally {
      setIsRefreshing(false)
    }
  }

  async function uploadDataset({ accessLevel, file, name }) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('access_level', accessLevel)
    if (name.trim()) {
      formData.append('name', name.trim())
    }

    const payload = await apiRequest('/datasets/upload/csv/', {
      method: 'POST',
      body: formData,
      csrfToken,
    })

    await Promise.all([refreshDatasets(), refreshExperiments()])
    return payload
  }

  async function deleteDataset(datasetId) {
    const payload = await apiRequest(`/datasets/${datasetId}/`, {
      method: 'DELETE',
      csrfToken,
    })

    await Promise.all([refreshDatasets(), refreshExperiments()])
    return payload
  }

  async function uploadScript({ accessLevel, file, mainClass, name }) {
    const formData = new FormData()
    formData.append('script', file)
    formData.append('access_level', accessLevel)

    if (name.trim()) {
      formData.append('name', name.trim())
    }

    if (mainClass.trim()) {
      formData.append('main_class', mainClass.trim())
    }

    const payload = await apiRequest('/scripts/upload/', {
      method: 'POST',
      body: formData,
      csrfToken,
    })

    await Promise.all([refreshScripts(), refreshExperiments()])
    return payload
  }

  async function deleteScript(scriptId) {
    const payload = await apiRequest(`/scripts/${scriptId}/`, {
      method: 'DELETE',
      csrfToken,
    })

    await Promise.all([refreshScripts(), refreshExperiments()])
    return payload
  }

  async function createExperiment({ datasetId, scriptId, args }) {
    const payload = await apiRequest('/experiments/create/', {
      method: 'POST',
      body: {
        dataset_id: datasetId,
        script_id: scriptId,
		args: args || '',
      },
      csrfToken,
    })

    await refreshExperiments()
    return payload
  }

  async function runExperiment(experimentId) {
    const payload = await apiRequest(`/experiments/${experimentId}/run/`, {
      method: 'POST',
      csrfToken,
    })

    await refreshExperiments()
    return payload
  }

  async function cancelExperiment(experimentId) {
    const payload = await apiRequest(`/experiments/${experimentId}/cancel/`, {
      method: 'POST',
      csrfToken,
    })

    await refreshExperiments()
    return payload
  }

  async function deleteExperiment(experimentId) {
    const payload = await apiRequest(`/experiments/${experimentId}/delete/`, {
      method: 'DELETE',
      csrfToken,
    })

    await refreshExperiments()
    return payload
  }

  async function loadExperimentDetail(experimentId) {
    return apiRequest(`/experiments/${experimentId}/`)
  }

  useEffect(() => {
    if (authLoading) {
      return
    }

    if (!isAuthenticated) {
      startTransition(() => {
        setDatasets([])
        setScripts([])
        setExperiments([])
      })
      setWorkspaceError('')
      return
    }

    refreshAll().catch(() => undefined)
  }, [authLoading, isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated) {
      return undefined
    }

    const intervalId = window.setInterval(() => {
      refreshExperiments().catch(() => undefined)
    }, 12000)

    return () => window.clearInterval(intervalId)
  }, [isAuthenticated])

  const summary = useMemo(() => {
    const ownedDatasets = datasets.filter((dataset) => dataset.owner === user?.username)
    const ownedScripts = scripts.filter((script) => script.owner === user?.username)
    const activeExperiments = experiments.filter((experiment) => ACTIVE_STATUSES.has(experiment.status))

    return {
      datasetCount: datasets.length,
      scriptCount: scripts.length,
      experimentCount: experiments.length,
      runningCount: experiments.filter((experiment) => experiment.status === 'Running').length,
      queuedCount: experiments.filter((experiment) => experiment.status === 'Queued').length,
      activeCount: activeExperiments.length,
      ownedDatasetCount: ownedDatasets.length,
      ownedScriptCount: ownedScripts.length,
      publicDatasetCount: datasets.filter((dataset) => dataset.access_level === 'public').length,
      publicScriptCount: scripts.filter((script) => script.access_level === 'public').length,
    }
  }, [datasets, experiments, scripts, user?.username])

  const value = {
    createExperiment,
    datasets,
    deleteDataset,
    cancelExperiment,
    deleteExperiment,
    deleteScript,
    downloadResultUrl: (path) => buildApiUrl(path),
    experiments,
    isRefreshing,
    loadExperimentDetail,
    refreshAll,
    refreshDatasets,
    refreshExperiments,
    refreshScripts,
    runExperiment,
    scripts,
    summary,
    uploadDataset,
    uploadScript,
    workspaceError,
  }

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used inside WorkspaceProvider')
  }
  return context
}