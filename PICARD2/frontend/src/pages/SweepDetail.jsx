import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import LcarsLayout from '../components/layout/LcarsLayout'
import StatusBadge from '../components/common/StatusBadge'
import { buildApiUrl } from '../lib/api'
import { useSweeps } from '../features/sweeps/SweepContext'
import { SweepBackLink, SweepProgress } from '../features/sweeps/SweepShared'
import SweepDialog from '../features/sweeps/SweepDialog'
import { describeError, isActive } from '../features/sweeps/sweepApi'
import { RUN_STATUSES, sweepCounts, sweepStatus } from '../features/sweeps/sweepModel'
import { usePolling } from '../features/sweeps/usePolling'
import '../features/sweeps/sweeps.css'

const PAGE_SIZE = 20
const runLabel = (run) => `Run #${String(run.sweep_index + 1).padStart(3, '0')}`

function RunDialog({ sweep, run, onClose }) {
  const { repository } = useSweeps()
  const [output, setOutput] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  // Load the run's log when the dialog opens, then follow it while it runs.
  useEffect(() => {
    let current = true
    repository.runDetail(run.id).then(
      (detail) => { if (current) setOutput(detail.output || '') },
      (issue) => { if (current) setError(describeError(issue)) },
    )
    return () => { current = false }
  }, [run.id, repository])
  usePolling(() => repository.runDetail(run.id).then((detail) => setOutput(detail.output || '')).catch(() => undefined), isActive(run.status))
  async function rerun() {
    setBusy(true); setError('')
    try { await repository.rerun(sweep.id, run.id); setOutput(null) } catch (issue) { setError(describeError(issue)) } finally { setBusy(false) }
  }
  return <SweepDialog title={runLabel(run)} onClose={onClose}>
    <div className="metadata-row"><StatusBadge status={run.status} /><span>{sweep.algorithm.name} · {sweep.dataset.name}</span></div>
    <p className="helper-text sweep-experiment-id">Experiment ID: {run.id}</p>
    <dl className="argument-values">{Object.entries(run.param_values).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
    {error ? <p className="message-banner message-banner-error" role="alert">{error}</p> : null}
    <div className="form-actions">
      {run.has_result ? <a className="action-button secondary tiny" href={buildApiUrl(run.result_url)}>Download result</a> : null}
      {['Failed', 'Cancelled'].includes(run.status) ? <button type="button" className="action-button tiny" disabled={busy} onClick={rerun}>{busy ? 'Queueing…' : 'Run again'}</button> : null}
    </div>
    <p className="lcars-eyebrow">Spark output</p>
    <pre className="detail-log sweep-output">{output === null ? 'Loading output…' : output || 'No output yet.'}</pre>
  </SweepDialog>
}

function SweepResults({ sweep }) {
  const [status, setStatus] = useState('All')
  const [page, setPage] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const runs = sweep.experiments ?? []
  const selected = runs.find((run) => run.id === selectedId)
  const axes = (sweep.axes ?? []).filter((axis) => axis.varied)
  const fixed = (sweep.axes ?? []).filter((axis) => !axis.varied)
  const results = runs.filter((run) => status === 'All' || run.status === status)
  const pages = Math.max(1, Math.ceil(results.length / PAGE_SIZE))
  const visiblePage = Math.min(page, pages - 1)
  return <section className="panel-card">
    <div className="panel-heading-row"><div><p className="lcars-eyebrow">Configurations & results</p><h2>Runs and results</h2></div><div className="sweep-table-controls">
      <label className="field"><span>Filter status</span><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(0) }}><option>All</option>{RUN_STATUSES.map((value) => <option key={value}>{value}</option>)}</select></label>
    </div></div>
    <p className="helper-text">Each run is an ordinary experiment. Select a run to see its full configuration and Spark output, download its result, or run it again.</p>
    {fixed.length ? <details className="sweep-fixed"><summary>Fixed parameter values ({fixed.length})</summary><dl className="argument-values">{fixed.map((axis) => <div key={axis.name}><dt>{axis.name}</dt><dd>{String(axis.values[0])}</dd></div>)}</dl></details> : null}
    <p className="helper-text sweep-table-hint">Swipe the table horizontally to see every parameter, status, and result.</p>
    {results.length ? <div className="sweep-table-scroll" role="region" aria-label="Sweep runs and results" tabIndex={0}>
      <table className="sweep-table"><caption>{results.length} {results.length === 1 ? 'run' : 'runs'}{status !== 'All' ? ` with status ${status}` : ''}. {axes.length ? 'Varied parameters shown; fixed settings above.' : 'Parameter values shown above.'}</caption>
        <thead><tr><th scope="col">Run</th>{axes.map((axis) => <th scope="col" key={axis.name}>{axis.name}</th>)}<th scope="col">Status</th><th scope="col">Result</th></tr></thead>
        <tbody>{results.slice(visiblePage * PAGE_SIZE, (visiblePage + 1) * PAGE_SIZE).map((run) => <tr key={run.id} className={run.status === 'Running' ? 'sweep-running-row' : ''}>
          <th scope="row"><button type="button" className="sweep-run-link" onClick={() => setSelectedId(run.id)}>{runLabel(run)}</button></th>
          {axes.map((axis) => <td key={axis.name}>{String(run.param_values[axis.name])}</td>)}<td><StatusBadge status={run.status} /></td>
          <td>{run.has_result ? <a href={buildApiUrl(run.result_url)}>Download</a> : '—'}</td>
        </tr>)}</tbody>
      </table></div> : <div className="empty-state">No runs have this status yet. Choose another status to see more runs.</div>}
    {pages > 1 ? <div className="sweep-pagination"><button type="button" className="action-button tiny secondary" disabled={!visiblePage} onClick={() => setPage(visiblePage - 1)}>Previous</button><span>Page {visiblePage + 1} of {pages}</span><button type="button" className="action-button tiny secondary" disabled={visiblePage + 1 === pages} onClick={() => setPage(visiblePage + 1)}>Next</button></div> : null}
    {selected ? <RunDialog sweep={sweep} run={selected} onClose={() => setSelectedId(null)} /> : null}
  </section>
}

function SweepMonitor({ sweep }) {
  const { repository, refreshExperiments } = useSweeps()
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const counts = sweepCounts(sweep)
  const status = sweepStatus(sweep)
  async function act(action) {
    setBusy(true); setError('')
    try {
      if (action === 'cancel') await repository.cancel(sweep.id)
      else { await repository.remove(sweep.id); navigate('/sweeps') }
      refreshExperiments().catch(() => undefined)
      setConfirming('')
    } catch (issue) { setError(describeError(issue)) } finally { setBusy(false) }
  }
  const active = isActive(status)
  return <>
    <section className="panel-card panel-card-accent"><div className="panel-heading-row"><div><p className="lcars-eyebrow">Sweep monitoring</p><h1>{sweep.name}</h1><p className="lead-copy">{sweep.algorithm.name} · {sweep.dataset.name}</p></div><StatusBadge status={status} /></div>
      <div className="metadata-row"><span>{counts.total} {counts.total === 1 ? 'run' : 'runs'}</span><span>Created {new Date(sweep.created_at).toLocaleString()}</span><span>Runs execute one at a time</span>{active ? <span>Refreshing every 4 s</span> : null}</div>
      <SweepProgress sweep={sweep} />
      <div className="detail-actions">
        <button type="button" className="action-button danger" disabled={busy || !counts.Queued} onClick={() => setConfirming('cancel')}>{!counts.Queued ? 'No queued runs to cancel' : `Cancel ${counts.Queued} queued runs`}</button>
        <button type="button" className="action-button secondary" disabled={busy || active} title={active ? 'Cancel the sweep and wait for running runs to finish first.' : undefined} onClick={() => setConfirming('delete')}>Delete sweep</button>
      </div>
      <p className="helper-text">Cancelling stops runs that are still queued; a run that has started finishes normally. A sweep can be deleted once nothing is queued or running.</p>
    </section>
    <div role="status" aria-live="polite" className={sweep.cancel_requested ? 'message-banner' : 'sr-only'}>{sweep.cancel_requested ? counts.Running ? 'Cancellation requested. Queued runs are cancelled; the active run will finish before this sweep becomes Cancelled.' : `Sweep ${status.toLowerCase()}. ${counts.Cancelled} runs were cancelled before execution.` : `Sweep ${status}. ${counts.completed} completed, ${counts.Running} running, ${counts.Queued} queued.`}</div>
    {error && !confirming ? <div className="message-banner message-banner-error" role="alert">{error}</div> : null}
    <section className="metric-grid sweep-counts" aria-label="Run counts">{[[counts.total, 'Total'], [counts.completed, 'Completed'], [counts.Success, 'Successful'], [counts.Failed, 'Failed'], [counts.Cancelled, 'Cancelled'], [counts.Queued, 'Queued'], [counts.Running, 'Running']].map(([value, label]) => <div className="metric-card" key={label}><span className="metric-label">{label}</span><strong className="metric-value">{String(value).padStart(2, '0')}</strong></div>)}</section>
    <SweepResults sweep={sweep} />
    {confirming ? <SweepDialog title={confirming === 'cancel' ? 'Cancel waiting runs?' : 'Delete this sweep?'} onClose={() => { if (!busy) setConfirming('') }}>
      {confirming === 'cancel' ? <>
        <p>This cancels the {counts.Queued} runs still queued in “{sweep.name}”. {counts.Running ? 'The active run will be allowed to finish.' : 'No run is currently active in this sweep.'}</p>
        <p>Cancelled runs never start. Completed results remain available.</p>
      </> : <p>This permanently deletes “{sweep.name}”, its {counts.total} runs, and their output and result files.</p>}
      {error ? <p className="message-banner message-banner-error" role="alert">{error}</p> : null}
      <div className="form-actions"><button type="button" className="action-button secondary" disabled={busy} onClick={() => setConfirming('')}>Keep it</button>
        <button type="button" className="action-button danger" disabled={busy} onClick={() => act(confirming)}>{busy ? 'Working…' : confirming === 'cancel' ? `Cancel ${counts.Queued} queued runs` : 'Delete sweep'}</button></div>
    </SweepDialog> : null}
  </>
}

export default function SweepDetail() {
  const { id } = useParams()
  const { state } = useLocation()
  const { details, repository } = useSweeps()
  const sweep = details[id]
  const [loadState, setLoadState] = useState({ id: null, error: '' })
  useEffect(() => {
    let current = true
    repository.load(id)
      .then(() => { if (current) setLoadState({ id, error: '' }) })
      .catch((issue) => { if (current) setLoadState({ id, error: describeError(issue) }) })
    return () => { current = false }
  }, [id, repository])
  // Keep refreshing until every run has settled; stops on unmount.
  usePolling(() => repository.load(id).catch(() => undefined), Boolean(sweep && isActive(sweepStatus(sweep))))
  const loaded = loadState.id === id
  return <LcarsLayout><SweepBackLink />
    {state?.notice ? <div className="message-banner message-banner-error" role="alert">{state.notice}</div> : null}
    {sweep ? <SweepMonitor key={sweep.id} sweep={sweep} />
      : !loaded ? <p className="message-banner" role="status">Loading sweep…</p>
        : <section className="panel-card empty-state"><h1>{loadState.error ? 'Unable to load this sweep' : 'Sweep not found'}</h1><p>{loadState.error || 'It may have been deleted, or it belongs to another account.'}</p></section>}
  </LcarsLayout>
}
