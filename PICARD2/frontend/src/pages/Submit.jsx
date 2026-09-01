import { useDeferredValue, useMemo, useState } from 'react'
import LcarsLayout from '../components/layout/LcarsLayout'
import { useAuth } from '../components/auth/AuthProvider'
import { useSound } from '../components/audio/SoundProvider'
import { useWorkspace } from '../components/workspace/WorkspaceProvider'

export default function Submit() {
  const { user } = useAuth()
  const { play } = useSound()
  const {
    createExperiment,
    datasets,
    deleteDataset,
    deleteScript,
    scripts,
    uploadDataset,
    uploadScript,
  } = useWorkspace()
  const [datasetForm, setDatasetForm] = useState({ accessLevel: 'private', file: null, name: '' })
  const [scriptForm, setScriptForm] = useState({ accessLevel: 'private', file: null, mainClass: '', name: '' })
  const [experimentForm, setExperimentForm] = useState({ datasetId: '', scriptId: '', args: '' })
  const [datasetSearch, setDatasetSearch] = useState('')
  const [scriptSearch, setScriptSearch] = useState('')
  const [feedback, setFeedback] = useState({ tone: '', text: '' })
  const [busyAction, setBusyAction] = useState('')

  const deferredDatasetSearch = useDeferredValue(datasetSearch)
  const deferredScriptSearch = useDeferredValue(scriptSearch)

  const filteredDatasets = useMemo(() => {
    return datasets.filter((dataset) => {
      const haystack = `${dataset.name} ${dataset.owner} ${dataset.file_name}`.toLowerCase()
      return haystack.includes(deferredDatasetSearch.trim().toLowerCase())
    })
  }, [datasets, deferredDatasetSearch])

  const filteredScripts = useMemo(() => {
    return scripts.filter((script) => {
      const haystack = `${script.name} ${script.owner} ${script.file_type}`.toLowerCase()
      return haystack.includes(deferredScriptSearch.trim().toLowerCase())
    })
  }, [deferredScriptSearch, scripts])

  const selectedAlgorithm = useMemo(
    () => scripts.find((script) => script.id === experimentForm.scriptId) || null,
    [experimentForm.scriptId, scripts],
  )

  async function handleDatasetUpload(event) {
    event.preventDefault()

    if (!datasetForm.file) {
      setFeedback({ tone: 'error', text: 'Select a CSV file before uploading a dataset.' })
      return
    }

    setBusyAction('dataset')
    setFeedback({ tone: '', text: '' })

    try {
      await play('confirm')
      await uploadDataset({
        accessLevel: datasetForm.accessLevel,
        file: datasetForm.file,
        name: datasetForm.name,
      })
      setDatasetForm({ accessLevel: 'private', file: null, name: '' })
      setFeedback({ tone: 'success', text: 'Dataset uploaded successfully.' })
    } catch (error) {
      setFeedback({ tone: 'error', text: error instanceof Error ? error.message : 'Dataset upload failed.' })
    } finally {
      setBusyAction('')
    }
  }

  async function handleScriptUpload(event) {
    event.preventDefault()

    if (!scriptForm.file) {
      setFeedback({ tone: 'error', text: 'Select a Python or JAR file before uploading an algorithm.' })
      return
    }

    const extension = scriptForm.file.name.split('.').pop()?.toLowerCase()
    if (!['py', 'jar'].includes(extension || '')) {
      setFeedback({ tone: 'error', text: 'Only .py and .jar uploads are supported.' })
      return
    }

    if (extension === 'jar' && !scriptForm.mainClass.trim()) {
      setFeedback({ tone: 'error', text: 'A main class is required for JAR uploads.' })
      return
    }

    setBusyAction('script')
    setFeedback({ tone: '', text: '' })

    try {
      await play('confirm')
      const result = await uploadScript({
        accessLevel: scriptForm.accessLevel,
        file: scriptForm.file,
        mainClass: scriptForm.mainClass,
        name: scriptForm.name,
      })
      if (result.recommended_args) {
        setExperimentForm((current) => ({
          ...current,
          scriptId: result.script_id,
          args: result.recommended_args,
        }))
      }
      setScriptForm({ accessLevel: 'private', file: null, mainClass: '', name: '' })
      setFeedback({ tone: 'success', text: 'Algorithm uploaded successfully.' })
    } catch (error) {
      setFeedback({ tone: 'error', text: error instanceof Error ? error.message : 'Algorithm upload failed.' })
    } finally {
      setBusyAction('')
    }
  }

  async function handleExperimentCreate(event) {
    event.preventDefault()

    if (!experimentForm.scriptId || !experimentForm.datasetId) {
      setFeedback({ tone: 'error', text: 'Select both a dataset and an algorithm before creating an experiment.' })
      return
    }

    if (selectedAlgorithm?.arguments_required && !experimentForm.args.trim()) {
      setFeedback({ tone: 'error', text: 'CoDRIFT arguments are required.' })
      return
    }

    setBusyAction('experiment')
    setFeedback({ tone: '', text: '' })

    try {
      await play('confirm')
      const result = await createExperiment({
        datasetId: experimentForm.datasetId,
        scriptId: experimentForm.scriptId,
        args: experimentForm.args,
      })
      setFeedback({ tone: 'success', text: `Experiment ${result.experiment_id} created and ready to queue.` })
    } catch (error) {
      setFeedback({ tone: 'error', text: error instanceof Error ? error.message : 'Experiment creation failed.' })
    } finally {
      setBusyAction('')
    }
  }

  async function handleDatasetDelete(datasetId) {
    if (!window.confirm('Delete this dataset? Existing experiments that reference it may no longer run correctly.')) {
      return
    }

    setBusyAction(`dataset-delete-${datasetId}`)

    try {
      await play('alert')
      await deleteDataset(datasetId)
      setFeedback({ tone: 'success', text: 'Dataset deleted.' })
    } catch (error) {
      setFeedback({ tone: 'error', text: error instanceof Error ? error.message : 'Dataset deletion failed.' })
    } finally {
      setBusyAction('')
    }
  }

  async function handleScriptDelete(scriptId) {
    if (!window.confirm('Delete this algorithm? Existing experiments that reference it may no longer run correctly.')) {
      return
    }

    setBusyAction(`script-delete-${scriptId}`)

    try {
      await play('alert')
      await deleteScript(scriptId)
      setFeedback({ tone: 'success', text: 'Algorithm deleted.' })
    } catch (error) {
      setFeedback({ tone: 'error', text: error instanceof Error ? error.message : 'Algorithm deletion failed.' })
    } finally {
      setBusyAction('')
    }
  }

  return (
    <LcarsLayout>
      <section className="panel-card panel-card-accent">
        <p className="lcars-eyebrow">Submission Bay</p>
        <h1>Datasets, algorithms, and experiment setup</h1>
        <p className="lead-copy">
          The workspace keeps uploads separate from execution. Build resource libraries here, then create
          experiments that can be queued and observed from the runs console.
        </p>
      </section>

      {feedback.text ? (
        <section className={`message-banner ${feedback.tone === 'error' ? 'message-banner-error' : 'message-banner-success'}`} role="status">
          {feedback.text}
        </section>
      ) : null}

      <section className="panel-grid two-up">
        <article className="panel-card">
          <p className="lcars-eyebrow">CSV Intake</p>
          <h2>Upload dataset</h2>
          <form className="lcars-form" onSubmit={handleDatasetUpload}>
            <div className="form-grid">
              <label className="field">
                <span>Display name</span>
                <input
                  type="text"
                  value={datasetForm.name}
                  onChange={(event) => setDatasetForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Optional dataset name"
                />
              </label>
              <label className="field">
                <span>Visibility</span>
                <select
                  value={datasetForm.accessLevel}
                  onChange={(event) => setDatasetForm((current) => ({ ...current, accessLevel: event.target.value }))}
                >
                  <option value="private">Private</option>
                  <option value="public">Public</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span>CSV file</span>
              <input type="file" accept=".csv,text/csv" onChange={(event) => setDatasetForm((current) => ({ ...current, file: event.target.files?.[0] || null }))} />
            </label>
            <div className="form-actions">
              <button type="submit" className="action-button" disabled={busyAction === 'dataset'}>
                {busyAction === 'dataset' ? 'Uploading...' : 'Upload Dataset'}
              </button>
            </div>
          </form>
        </article>

        <article className="panel-card">
          <p className="lcars-eyebrow">Algorithm Intake</p>
          <h2>Upload script or JAR</h2>
          <form className="lcars-form" onSubmit={handleScriptUpload}>
            <div className="form-grid">
              <label className="field">
                <span>Display name</span>
                <input
                  type="text"
                  value={scriptForm.name}
                  onChange={(event) => setScriptForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Optional algorithm name"
                />
              </label>
              <label className="field">
                <span>JAR main class</span>
                <input
                  type="text"
                  value={scriptForm.mainClass}
                  onChange={(event) => setScriptForm((current) => ({ ...current, mainClass: event.target.value }))}
                  placeholder="Required for .jar uploads"
                />
              </label>
              <label className="field">
                <span>Visibility</span>
                <select
                  value={scriptForm.accessLevel}
                  onChange={(event) => setScriptForm((current) => ({ ...current, accessLevel: event.target.value }))}
                >
                  <option value="private">Private</option>
                  <option value="public">Public</option>
                </select>
              </label>
            </div>
            <label className="field">
              <span>Algorithm file</span>
              <input type="file" accept=".py,.jar" onChange={(event) => setScriptForm((current) => ({ ...current, file: event.target.files?.[0] || null }))} />
            </label>
            <p className="helper-text">Supported formats: Python scripts and runnable Spark JARs only.</p>
            <div className="form-actions">
              <button type="submit" className="action-button" disabled={busyAction === 'script'}>
                {busyAction === 'script' ? 'Uploading...' : 'Upload Algorithm'}
              </button>
            </div>
          </form>
        </article>
      </section>

      <section className="panel-card">
        <p className="lcars-eyebrow">Experiment Construction</p>
        <h2>Create an experiment record</h2>
        <form className="lcars-form" onSubmit={handleExperimentCreate}>
          <div className="form-grid two-columns">
            <label className="field">
              <span>Algorithm</span>
              <select
                value={experimentForm.scriptId}
                onChange={(event) => {
                  const scriptId = event.target.value
                  const script = scripts.find((candidate) => candidate.id === scriptId)
                  setExperimentForm((current) => ({
                    ...current,
                    scriptId,
                    args: script?.recommended_args || '',
                  }))
                }}
              >
                <option value="">Select an algorithm</option>
                {scripts.map((script) => (
                  <option key={script.id} value={script.id}>
                    {script.name} • {script.owner} • {script.access_level}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Dataset</span>
              <select
                value={experimentForm.datasetId}
                onChange={(event) => setExperimentForm((current) => ({ ...current, datasetId: event.target.value }))}
              >
                <option value="">Select a dataset</option>
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name} • {dataset.owner} • {dataset.access_level}
                  </option>
                ))}
              </select>
            </label>
            <label className="field" style={{ marginTop: '1rem' }}>
              <span>Arguments{selectedAlgorithm?.arguments_required ? ' (Required)' : ''}</span>
              <input
                type="text"
                value={experimentForm.args}
                onChange={(event) => setExperimentForm((current) => ({ ...current, args: event.target.value }))}
                placeholder={selectedAlgorithm?.recommended_args || 'Algorithm arguments'}
                required={Boolean(selectedAlgorithm?.arguments_required)}
              />
            </label>
          </div>
          {selectedAlgorithm?.is_codrift ? (
            <p className="helper-text">
              CoDRIFT order: numClasses numTrees impurity maxDepth maxBins percentLabeled k. Recommended: {selectedAlgorithm.recommended_args}.
            </p>
          ) : null}
          <p className="helper-text">New experiments are created in a pending state. Queue or re-run them from the runs console.</p>
          <div className="form-actions">
            <button type="submit" className="action-button" disabled={busyAction === 'experiment'}>
              {busyAction === 'experiment' ? 'Creating...' : 'Create Experiment'}
            </button>
          </div>
        </form>
      </section>

      <section className="panel-grid two-up">
        <article className="panel-card">
          <div className="panel-heading-row">
            <div>
              <p className="lcars-eyebrow">Dataset Library</p>
              <h2>Available CSV assets</h2>
            </div>
            <label className="field field-compact">
              <span className="sr-only">Search datasets</span>
              <input type="search" value={datasetSearch} onChange={(event) => setDatasetSearch(event.target.value)} placeholder="Search datasets" />
            </label>
          </div>
          {filteredDatasets.length ? (
            <ul className="resource-list">
              {filteredDatasets.map((dataset) => {
                const owned = dataset.owner === user?.username
                return (
                  <li key={dataset.id} className="resource-item">
                    <div>
                      <strong>{dataset.name}</strong>
                      <p className="resource-meta">{dataset.file_name} • {dataset.owner}</p>
                    </div>
                    <div className="resource-actions">
                      <span className={`access-pill ${dataset.access_level}`}>{dataset.access_level}</span>
                      {owned ? (
                        <button
                          type="button"
                          className="action-button danger tiny"
                          onClick={() => handleDatasetDelete(dataset.id)}
                          disabled={busyAction === `dataset-delete-${dataset.id}`}
                        >
                          Delete
                        </button>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            <div className="empty-state">No datasets match the current filter.</div>
          )}
        </article>

        <article className="panel-card">
          <div className="panel-heading-row">
            <div>
              <p className="lcars-eyebrow">Algorithm Library</p>
              <h2>Available scripts and JARs</h2>
            </div>
            <label className="field field-compact">
              <span className="sr-only">Search algorithms</span>
              <input type="search" value={scriptSearch} onChange={(event) => setScriptSearch(event.target.value)} placeholder="Search algorithms" />
            </label>
          </div>
          {filteredScripts.length ? (
            <ul className="resource-list">
              {filteredScripts.map((script) => {
                const owned = script.owner === user?.username
                return (
                  <li key={script.id} className="resource-item">
                    <div>
                      <strong>{script.name}</strong>
                      <p className="resource-meta">{script.file_type.toUpperCase()} • {script.owner}</p>
                    </div>
                    <div className="resource-actions">
                      <span className={`access-pill ${script.access_level}`}>{script.access_level}</span>
                      {owned ? (
                        <button
                          type="button"
                          className="action-button danger tiny"
                          onClick={() => handleScriptDelete(script.id)}
                          disabled={busyAction === `script-delete-${script.id}`}
                        >
                          Delete
                        </button>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            <div className="empty-state">No algorithms match the current filter.</div>
          )}
        </article>
      </section>
    </LcarsLayout>
  )
}
