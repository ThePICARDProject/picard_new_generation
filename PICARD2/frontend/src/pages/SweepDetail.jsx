import { useState } from 'react'
import { useParams } from 'react-router-dom'
import LcarsLayout from '../components/layout/LcarsLayout'
import StatusBadge from '../components/common/StatusBadge'
import { useSweeps } from '../features/sweeps/SweepContext'
import { SweepBackLink, SweepNotice, SweepProgress } from '../features/sweeps/SweepShared'
import SweepDialog from '../features/sweeps/SweepDialog'
import { RUN_STATUSES, sweepCounts, sweepStatus } from '../features/sweeps/sweepModel'
import '../features/sweeps/sweeps.css'

function SweepResults({ sweep }) {
  const [status, setStatus] = useState('All')
  const [sort, setSort] = useState('sequence')
  const [page, setPage] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const selected = sweep.experiments.find((run) => run.id === selectedId)
  const axes = sweep.axes.filter((axis) => axis.varied)
  const fixed = sweep.axes.filter((axis) => !axis.varied)
  const results = sweep.experiments.filter((run) => status === 'All' || run.status === status)
    .sort((a, b) => sort === 'accuracy' ? (b.metrics?.accuracy ?? -1) - (a.metrics?.accuracy ?? -1) || a.sweep_index - b.sweep_index : a.sweep_index - b.sweep_index)
  const pages = Math.max(1, Math.ceil(results.length / 20))
  const visiblePage = Math.min(page, pages - 1)
  const best = sweep.experiments.filter((run) => run.metrics).sort((a, b) => b.metrics.accuracy - a.metrics.accuracy)[0]
  return <section className="panel-card">
    <div className="panel-heading-row"><div><p className="lcars-eyebrow">Configurations & results</p><h2>Runs and results</h2></div><div className="sweep-table-controls">
      <label className="field"><span>Filter status</span><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(0) }}><option>All</option>{RUN_STATUSES.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label className="field"><span>Sort runs</span><select value={sort} onChange={(event) => { setSort(event.target.value); setPage(0) }}><option value="sequence">Generation order</option><option value="accuracy">Highest accuracy</option></select></label>
    </div></div>
    <p className="helper-text">Accuracy and duration are simulated demo metrics. Select a run to inspect its complete configuration and output.</p>
    {best ? <div className="sweep-best"><span>Best mock accuracy</span><strong>{(best.metrics.accuracy * 100).toFixed(1)}%</strong><button type="button" className="action-button secondary tiny" onClick={() => setSelectedId(best.id)}>Inspect run #{best.sweep_index}</button></div> : null}
    {fixed.length ? <details className="sweep-fixed"><summary>Fixed parameter values ({fixed.length})</summary><dl className="argument-values">{fixed.map((axis) => <div key={axis.name}><dt>{axis.name}</dt><dd>{String(axis.values[0])}</dd></div>)}</dl></details> : null}
    <p className="helper-text sweep-table-hint">Swipe the table horizontally to see every parameter, status, and result.</p>
    {results.length ? <div className="sweep-table-scroll" role="region" aria-label="Experiment runs and results" tabIndex={0}>
      <table className="sweep-table"><caption>{results.length} {results.length === 1 ? 'run' : 'runs'}{status !== 'All' ? ` with status ${status}` : ''}. {axes.length ? 'Varied parameters shown; fixed settings above.' : 'Parameter values shown above.'}</caption>
        <thead><tr><th scope="col">Run</th>{axes.map((axis) => <th scope="col" key={axis.name}>{axis.name}</th>)}<th scope="col">Status</th><th scope="col">Accuracy</th><th scope="col">Duration</th></tr></thead>
        <tbody>{results.slice(visiblePage * 20, (visiblePage + 1) * 20).map((run) => <tr key={run.id} className={run.status === 'Running' ? 'sweep-running-row' : ''}>
          <th scope="row"><button type="button" className="sweep-run-link" onClick={() => setSelectedId(run.id)}>Run #{String(run.sweep_index).padStart(3, '0')}</button></th>
          {axes.map((axis) => <td key={axis.name}>{String(run.param_values[axis.name])}</td>)}<td><StatusBadge status={run.status} /></td><td>{run.metrics ? `${(run.metrics.accuracy * 100).toFixed(1)}%` : '—'}</td><td>{run.metrics ? `${run.metrics.duration_seconds}s` : '—'}</td>
        </tr>)}</tbody>
      </table></div> : <div className="empty-state">No runs have this status yet. Choose another status to see more runs.</div>}
    {pages > 1 ? <div className="sweep-pagination"><button type="button" className="action-button tiny secondary" disabled={!visiblePage} onClick={() => setPage(visiblePage - 1)}>Previous</button><span>Page {visiblePage + 1} of {pages}</span><button type="button" className="action-button tiny secondary" disabled={visiblePage + 1 === pages} onClick={() => setPage(visiblePage + 1)}>Next</button></div> : null}
    {selected ? <SweepDialog title={`Run #${selected.sweep_index}`} onClose={() => setSelectedId(null)}>
      <div className="metadata-row"><StatusBadge status={selected.status} /><span>{sweep.algorithm.name} · {sweep.dataset.name}</span></div>
      <p className="helper-text sweep-experiment-id">ID: {selected.id}</p>
      <dl className="argument-values">{Object.entries(selected.param_values).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
      {selected.metrics ? <p>Mock accuracy: <strong>{(selected.metrics.accuracy * 100).toFixed(1)}%</strong> · Duration: {selected.metrics.duration_seconds}s</p> : null}
      <p className="lcars-eyebrow">Simulated output</p><pre className="detail-log sweep-output">{selected.output}</pre>
    </SweepDialog> : null}
  </section>
}

function SweepMonitor({ sweep }) {
  const { repository } = useSweeps()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const counts = sweepCounts(sweep)
  const status = sweepStatus(sweep)
  async function cancel() {
    setBusy(true); setError('')
    try { await repository.cancel(sweep.id); setConfirming(false) }
    catch (issue) { setError(issue.message) }
    finally { setBusy(false) }
  }
  return <>
    <section className="panel-card panel-card-accent"><div className="panel-heading-row"><div><p className="lcars-eyebrow">Experiment monitoring</p><h1>{sweep.name}</h1><p className="lead-copy">{sweep.algorithm.name} · {sweep.dataset.name}</p></div><StatusBadge status={status} /></div>
      <div className="metadata-row"><span>{counts.total} {counts.total === 1 ? 'run' : 'runs'}</span><span>Created {new Date(sweep.created_at).toLocaleString()}</span><span>One run at a time</span></div>
      <SweepProgress sweep={sweep} />
      <div className="detail-actions"><button type="button" className="action-button danger" disabled={busy || !counts.Queued || sweep.cancel_requested} onClick={() => setConfirming(true)}>{sweep.cancel_requested ? 'Cancellation requested' : !counts.Queued ? 'No queued runs to cancel' : 'Cancel queued runs'}</button></div>
      <p className="helper-text">Active runs finish normally. Cancellation only stops runs that are still queued.</p>
    </section>
    <div role="status" aria-live="polite" className={sweep.cancel_requested ? 'message-banner' : 'sr-only'}>{sweep.cancel_requested ? counts.Running ? 'Cancellation requested. Queued runs are cancelled; the active run will finish before this experiment becomes Cancelled.' : `Experiment ${status.toLowerCase()}. ${counts.Cancelled} runs were cancelled before execution.` : `Experiment ${status}. ${counts.completed} completed, ${counts.Running} running, ${counts.Queued} queued.`}</div>
    {error && !confirming ? <div className="message-banner message-banner-error" role="alert">{error}</div> : null}
    <section className="metric-grid sweep-counts" aria-label="Run counts">{[[counts.total, 'Total'], [counts.completed, 'Completed'], [counts.Success, 'Successful'], [counts.Failed, 'Failed'], [counts.Cancelled, 'Cancelled'], [counts.Queued, 'Queued'], [counts.Running, 'Running'], [counts.Pending, 'Pending']].map(([value, label]) => <div className="metric-card" key={label}><span className="metric-label">{label}</span><strong className="metric-value">{String(value).padStart(2, '0')}</strong></div>)}</section>
    <SweepResults sweep={sweep} />
    {confirming ? <SweepDialog title="Cancel waiting runs?" onClose={() => { if (!busy) setConfirming(false) }}>
      <p>This will cancel the {counts.Queued} runs still queued in “{sweep.name}”. {counts.Running ? 'The active run will be allowed to finish.' : 'No run is currently active in this experiment.'}</p>
      <p>Cancelled runs will never start. Completed results remain available.</p>
      {error ? <p className="message-banner message-banner-error" role="alert">{error}</p> : null}
      <div className="form-actions"><button type="button" className="action-button secondary" disabled={busy} onClick={() => setConfirming(false)}>Keep running</button><button type="button" className="action-button danger" disabled={busy || !counts.Queued} onClick={cancel}>{busy ? 'Cancelling…' : `Cancel ${counts.Queued} queued runs`}</button></div>
    </SweepDialog> : null}
  </>
}

export default function SweepDetail() {
  const { id } = useParams()
  const { sweeps, error, loading } = useSweeps()
  const sweep = sweeps.find((item) => item.id === id)
  return <LcarsLayout><SweepBackLink /><SweepNotice />{loading ? <p className="message-banner" role="status">Loading saved experiment…</p> : sweep ? <SweepMonitor key={sweep.id} sweep={sweep} /> : <section className="panel-card empty-state"><h1>{error ? 'Unable to load this experiment' : 'Experiment not found'}</h1><p>{error ? 'Resolve the storage issue above and retry.' : 'This experiment may belong to another browser or may have been removed. Return to all experiments to create one.'}</p></section>}</LcarsLayout>
}
