import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import LcarsLayout from '../components/layout/LcarsLayout'
import { getArgumentDefinitions } from '../lib/argumentDefinitions'
import { useSweeps } from '../features/sweeps/SweepContext'
import { SweepBackLink, SweepNotice } from '../features/sweeps/SweepShared'
import ParameterField from '../features/sweeps/ParameterField'
import { buildSweepPlan, initialConfiguration, MAX_EXPERIMENTS } from '../features/sweeps/sweepModel'
import '../features/sweeps/sweeps.css'

function SweepBuilder() {
  const { algorithms, datasets, repository, error: storageError } = useSweeps()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [algorithmId, setAlgorithmId] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [configuration, setConfiguration] = useState({})
  const [parameterSweep, setParameterSweep] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [previewPage, setPreviewPage] = useState(0)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const algorithm = algorithms.find((item) => String(item.id) === algorithmId)
  const dataset = datasets.find((item) => String(item.id) === datasetId)
  const definitions = getArgumentDefinitions(algorithm)
  const plan = useMemo(() => definitions ? buildSweepPlan(definitions, configuration, { varyParameters: parameterSweep }) : null, [definitions, configuration, parameterSweep])
  const canReview = Boolean(name.trim() && algorithm && dataset && plan && !plan.error)
  function update(parameter, patch) {
    setConfiguration((current) => ({ ...current, [parameter]: { ...current[parameter], ...patch } }))
    setError('')
  }
  function review(event) {
    event.preventDefault()
    if (!canReview) { setError('Enter a name, choose both assets, and resolve the parameter errors.'); return }
    setReviewing(true)
    setPreviewPage(0)
    setError('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  async function submit() {
    setSubmitting(true)
    setError('')
    try {
      const sweep = await repository.create({ name, algorithm, dataset, configuration, parameterSweep })
      navigate(`/experiment/${sweep.id}`)
    } catch (issue) { setError(issue.message) } finally { setSubmitting(false) }
  }
  return <>
    <section className="panel-card panel-card-accent"><p className="lcars-eyebrow">Experiment setup</p><h1>{reviewing ? 'Review your experiment' : 'Create an experiment'}</h1><p className="lead-copy">{reviewing ? 'Check the configuration before adding your runs to the queue.' : 'Choose an algorithm, a dataset, and parameter values. You can explore multiple combinations in the same experiment.'}</p>
      <ol className="sweep-steps" aria-label="Creation steps"><li className={!reviewing ? 'current' : ''} aria-current={!reviewing ? 'step' : undefined}>01 · Configure</li><li className={reviewing ? 'current' : ''} aria-current={reviewing ? 'step' : undefined}>02 · Review</li><li>03 · Launch & monitor</li></ol></section>
    {error ? <div className="message-banner message-banner-error" role="alert">{error}</div> : null}
    {!reviewing ? <form className="sweep-builder" onSubmit={review}>
      <section className="panel-card"><p className="lcars-eyebrow">01 / Algorithm & data</p><h2>Configure algorithm and dataset</h2><div className="lcars-form">
        <label className="field"><span>Experiment name</span><input required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. CoDRIFT Hyperparameter Test" /></label>
        <div className="form-grid two-columns"><label className="field"><span>Algorithm</span><select required value={algorithmId} onChange={(event) => {
          const id = event.target.value, selected = algorithms.find((item) => String(item.id) === id)
          setAlgorithmId(id); setConfiguration(initialConfiguration(getArgumentDefinitions(selected) || [])); setError('')
        }}><option value="">Select an algorithm</option>{algorithms.map((item) => <option key={item.id} value={item.id} disabled={!getArgumentDefinitions(item)?.length}>{item.name}{!getArgumentDefinitions(item)?.length ? ' — parameter manifest required' : ''}</option>)}</select></label>
          <label className="field"><span>Dataset</span><select required value={datasetId} onChange={(event) => setDatasetId(event.target.value)}><option value="">Select a dataset</option>{datasets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
        {!algorithms.length || !datasets.length ? <p className="empty-state">Upload algorithms with a parameter manifest and CSV datasets in the submission bay to get started.</p> : null}
        {algorithm?.algorithm_config?.input_description ? <p className="helper-text">Dataset requirements: {algorithm.algorithm_config.input_description}</p> : null}
      </div></section>
      {definitions?.length ? <section className="panel-card"><div className="panel-heading-row"><div><p className="lcars-eyebrow">02 / Configuration</p><h2>Algorithm parameters</h2></div><button type="button" className="action-button secondary tiny" onClick={() => setConfiguration(initialConfiguration(definitions))}>Reset defaults</button></div>
        <div className="sweep-option"><label className="sweep-toggle"><input type="checkbox" checked={parameterSweep} aria-describedby="parameter-sweep-help" onChange={(event) => { setParameterSweep(event.target.checked); setError('') }} /><span>Configure a parameter sweep</span></label><p id="parameter-sweep-help" className="helper-text">Try multiple values for selected parameters. Each combination becomes a separate run.</p></div>
        <p className="helper-text">{parameterSweep ? 'Enable “Vary” for each parameter to explore. All other parameters keep the fixed values shown below.' : 'Choose one value for each parameter. Defaults are filled in for you.'}</p>
        <div className="sweep-parameter-grid">{definitions.map((parameter) => <ParameterField key={parameter.name} parameter={parameter} allowVariation={parameterSweep} configuration={{ ...configuration[parameter.name], vary: parameterSweep && configuration[parameter.name].vary }} error={plan.errors[parameter.name]} onChange={(patch) => update(parameter.name, patch)} />)}</div>
      </section> : null}
      <section className="panel-card sweep-launch-summary"><div><p className="lcars-eyebrow">Execution preview</p><h2>{plan?.count ? `${plan.count.toLocaleString()} ${plan.count === 1 ? 'run' : 'runs'}` : 'Choose your configuration'}</h2>
        {plan?.varied.length ? <p className="sweep-equation">{plan.varied.map((axis) => `${axis.values.length} (${axis.name})`).join(' × ')} = <strong>{plan.count.toLocaleString()} runs</strong></p> : null}
        <p className="helper-text" role="status">{plan?.error || (parameterSweep ? `Cartesian product · Maximum ${MAX_EXPERIMENTS} runs per experiment` : 'One run with your configured parameter values.')}</p></div>
        <button className="action-button" type="submit" disabled={!canReview}>{parameterSweep ? 'Review combinations →' : 'Review experiment →'}</button></section>
    </form> : <>
      <section className="panel-card"><div className="panel-heading-row"><div><p className="lcars-eyebrow">Ready for launch</p><h2>{name.trim()}</h2><p>{algorithm.name} · {dataset.name}</p></div><strong className="sweep-total">{plan.count}<small>{plan.count === 1 ? 'run' : 'runs'}</small></strong></div>
        {parameterSweep ? <p className="sweep-equation">{plan.varied.map((axis) => `${axis.values.length} (${axis.name})`).join(' × ')} = <strong>{plan.count} runs</strong></p> : null}
        <p className="helper-text sweep-table-hint">Swipe the table horizontally to inspect all parameter values.</p>
        <div className="sweep-table-scroll" tabIndex={0} role="region" aria-label="Configured runs"><table className="sweep-table"><caption>All parameter values, including fixed settings. {plan.count} {plan.count === 1 ? 'run' : 'unique runs'}.</caption><thead><tr><th scope="col">Run</th>{definitions.map((parameter) => <th scope="col" key={parameter.name}>{parameter.name}{parameterSweep && configuration[parameter.name].vary ? <span className="sweep-column-note">varied</span> : <span className="sweep-column-note">fixed</span>}</th>)}</tr></thead><tbody>
          {plan.combinations.slice(previewPage * 20, (previewPage + 1) * 20).map((values, index) => <tr key={index}><th scope="row">#{previewPage * 20 + index + 1}</th>{definitions.map((parameter) => <td key={parameter.name}>{String(values[parameter.name])}</td>)}</tr>)}
        </tbody></table></div>
        {plan.count > 20 ? <div className="sweep-pagination"><button className="action-button secondary tiny" disabled={!previewPage} onClick={() => setPreviewPage((page) => page - 1)}>Previous</button><span>Page {previewPage + 1} of {Math.ceil(plan.count / 20)}</span><button className="action-button secondary tiny" disabled={(previewPage + 1) * 20 >= plan.count} onClick={() => setPreviewPage((page) => page + 1)}>Next</button></div> : null}
        <p className="helper-text">{parameterSweep ? 'Runs enter the queue in this order. Only one runs at a time. You can cancel waiting runs after launch.' : 'Your experiment will be queued with the parameter values shown above.'}</p>
        <div className="form-actions"><button type="button" className="action-button secondary" disabled={submitting} onClick={() => setReviewing(false)}>← Edit configuration</button><button type="button" className="action-button" disabled={submitting || !repository.available || Boolean(storageError)} onClick={submit}>{submitting ? 'Creating experiment…' : parameterSweep ? `Launch ${plan.count} runs` : 'Launch experiment'}</button></div>
      </section>
    </>}
  </>
}

export default function SweepCreate() {
  return <LcarsLayout><SweepBackLink /><SweepNotice /><SweepBuilder /></LcarsLayout>
}
