import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import LcarsLayout from '../components/layout/LcarsLayout'
import StatusBadge from '../components/common/StatusBadge'
import { useSound } from '../components/audio/SoundProvider'
import { useWorkspace } from '../components/workspace/WorkspaceProvider'

export default function Experiments() {
  const { play } = useSound()
  const {
    deleteExperiment,
    downloadResultUrl,
    experiments,
    loadExperimentDetail,
    refreshExperiments,
    runExperiment,
  } = useWorkspace()
  const [selectedExperimentId, setSelectedExperimentId] = useState(null)
  const [experimentDetail, setExperimentDetail] = useState(null)
  const [feedback, setFeedback] = useState({ tone: '', text: '' })
  const [detailError, setDetailError] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [searchValue, setSearchValue] = useState('')
  const logOutputRef = useRef(null)

  const deferredSearchValue = useDeferredValue(searchValue)

  const filteredExperiments = useMemo(() => {
    return experiments.filter((experiment) => {
      const haystack = `${experiment.script_name} ${experiment.dataset_name} ${experiment.status}`.toLowerCase()
      return haystack.includes(deferredSearchValue.trim().toLowerCase())
    })
  }, [deferredSearchValue, experiments])

  useEffect(() => {
    if (!filteredExperiments.length) {
      setSelectedExperimentId(null)
      setExperimentDetail(null)
      return
    }

    const selectedStillVisible = filteredExperiments.some((experiment) => experiment.id === selectedExperimentId)
    if (!selectedStillVisible) {
      setSelectedExperimentId(filteredExperiments[0].id)
    }
  }, [filteredExperiments, selectedExperimentId])

  useEffect(() => {
    if (!selectedExperimentId) {
      return undefined
    }

    let cancelled = false

    async function fetchDetail() {
      try {
        const detail = await loadExperimentDetail(selectedExperimentId)
        if (!cancelled) {
          setExperimentDetail(detail)
          setDetailError('')
        }
      } catch (error) {
        if (!cancelled) {
          setDetailError(error instanceof Error ? error.message : 'Unable to load experiment detail.')
        }
      }
    }

    fetchDetail()

    return () => {
      cancelled = true
    }
  }, [loadExperimentDetail, selectedExperimentId])

  useEffect(() => {
    if (!selectedExperimentId || !experimentDetail) {
      return undefined
    }

    if (!['Pending', 'Queued', 'Running'].includes(experimentDetail.status)) {
      return undefined
    }

    const intervalId = window.setInterval(() => {
      loadExperimentDetail(selectedExperimentId)
        .then((detail) => {
          setExperimentDetail(detail)
          setDetailError('')
        })
        .catch((error) => {
          setDetailError(error instanceof Error ? error.message : 'Unable to refresh experiment detail.')
        })

      refreshExperiments().catch(() => undefined)
    }, 4000)

    return () => window.clearInterval(intervalId)
  }, [experimentDetail, loadExperimentDetail, refreshExperiments, selectedExperimentId])

  useEffect(() => {
    const logOutput = logOutputRef.current
    if (logOutput) {
      logOutput.scrollTop = logOutput.scrollHeight
    }
  }, [experimentDetail?.id, experimentDetail?.output])

  async function handleRun(experimentId) {
    setBusyAction(`run-${experimentId}`)
    setFeedback({ tone: '', text: '' })

    try {
      await play('confirm')
      await runExperiment(experimentId)
      const detail = await loadExperimentDetail(experimentId)
      setExperimentDetail(detail)
      setFeedback({ tone: 'success', text: `Experiment ${experimentId} added to the queue.` })
    } catch (error) {
      setFeedback({ tone: 'error', text: error instanceof Error ? error.message : 'Unable to queue experiment.' })
    } finally {
      setBusyAction('')
    }
  }

  async function handleDelete(experimentId) {
    if (!window.confirm('Delete this experiment and remove any saved result artifact?')) {
      return
    }

    setBusyAction(`delete-${experimentId}`)
    setFeedback({ tone: '', text: '' })

    try {
      await play('alert')
      await deleteExperiment(experimentId)
      setFeedback({ tone: 'success', text: `Experiment ${experimentId} deleted.` })
      setExperimentDetail(null)
    } catch (error) {
      setFeedback({ tone: 'error', text: error instanceof Error ? error.message : 'Unable to delete experiment.' })
    } finally {
      setBusyAction('')
    }
  }

  return (
    <LcarsLayout>
      <section className="panel-card panel-card-accent">
        <p className="lcars-eyebrow">Runs Console</p>
        <h1>Experiment monitoring and result inspection</h1>
        <p className="lead-copy">
          Queue pending experiments, re-run completed jobs, and watch live output while Spark writes back logs.
        </p>
      </section>

      {feedback.text ? (
        <section className={`message-banner ${feedback.tone === 'error' ? 'message-banner-error' : 'message-banner-success'}`} role="status">
          {feedback.text}
        </section>
      ) : null}

      <section className="panel-grid list-detail-layout">
        <article className="panel-card list-panel">
          <div className="panel-heading-row">
            <div>
              <p className="lcars-eyebrow">Run Catalog</p>
              <h2>Existing experiments</h2>
            </div>
            <label className="field field-compact">
              <span className="sr-only">Search experiments</span>
              <input type="search" value={searchValue} onChange={(event) => setSearchValue(event.target.value)} placeholder="Search runs" />
            </label>
          </div>

          {filteredExperiments.length ? (
            <ul className="experiment-list">
              {filteredExperiments.map((experiment) => {
                const selected = experiment.id === selectedExperimentId
                return (
                  <li key={experiment.id}>
                    <button
                      type="button"
                      className={`experiment-row ${selected ? 'selected' : ''}`}
                      onClick={() => setSelectedExperimentId(experiment.id)}
                    >
                      <div>
                        <strong>{experiment.script_name}</strong>
                        <p>{experiment.dataset_name || 'No dataset attached'}</p>
                      </div>
                      <StatusBadge status={experiment.status} />
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <div className="empty-state">
              No experiments match the current filter. Create one from the submission bay first.
            </div>
          )}
        </article>

        <article className="panel-card detail-panel">
          <p className="lcars-eyebrow">Detail Feed</p>
          {experimentDetail ? (
            <>
              <div className="detail-header">
                <div>
                  <h2>{experimentDetail.script_name}</h2>
                  <p>{experimentDetail.dataset_name || 'No dataset attached'}</p>
                </div>
                <StatusBadge status={experimentDetail.status} />
              </div>

              <div className="detail-actions">
                <button
                  type="button"
                  className="action-button"
                  onClick={() => handleRun(experimentDetail.id)}
                  disabled={busyAction === `run-${experimentDetail.id}`}
                >
                  {busyAction === `run-${experimentDetail.id}` ? 'Queueing...' : 'Run / Re-run'}
                </button>
                {experimentDetail.has_result ? (
                  <a className="action-button secondary" href={downloadResultUrl(experimentDetail.result_url)}>
                    Download Result
                  </a>
                ) : null}
                <button
                  type="button"
                  className="action-button danger"
                  onClick={() => handleDelete(experimentDetail.id)}
                  disabled={busyAction === `delete-${experimentDetail.id}`}
                >
                  {busyAction === `delete-${experimentDetail.id}` ? 'Deleting...' : 'Delete'}
                </button>
              </div>

              <div className="metadata-row">
                <span>Experiment #{experimentDetail.id}</span>
                <span>{new Date(experimentDetail.created_at).toLocaleString()}</span>
              </div>

              {detailError ? <div className="message-banner message-banner-error">{detailError}</div> : null}

              <div className="log-panel">
                <p className="lcars-eyebrow">Live Output</p>
                <pre ref={logOutputRef} className="detail-log">{experimentDetail.output || 'No output has been recorded yet.'}</pre>
              </div>
            </>
          ) : (
            <div className="empty-state">Select an experiment to inspect status, logs, and result downloads.</div>
          )}
        </article>
      </section>
    </LcarsLayout>
  )
}
