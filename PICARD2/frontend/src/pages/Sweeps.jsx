import { useState } from 'react'
import { Link } from 'react-router-dom'
import LcarsLayout from '../components/layout/LcarsLayout'
import StatusBadge from '../components/common/StatusBadge'
import { useSweeps } from '../features/sweeps/SweepContext'
import { SweepNotice, SweepProgress } from '../features/sweeps/SweepShared'
import { sweepCounts, sweepStatus } from '../features/sweeps/sweepModel'
import '../features/sweeps/sweeps.css'

export default function Sweeps() {
  const { sweeps, loading } = useSweeps()
  const [search, setSearch] = useState('')
  const filtered = sweeps.filter((sweep) => `${sweep.name} ${sweep.algorithm.name} ${sweep.dataset.name} ${sweepStatus(sweep)}`.toLowerCase().includes(search.trim().toLowerCase()))
  const totalRuns = sweeps.reduce((sum, sweep) => sum + sweep.experiments.length, 0)
  const active = sweeps.filter((sweep) => ['Running', 'Queued'].includes(sweepStatus(sweep))).length
  const successful = sweeps.reduce((sum, sweep) => sum + sweepCounts(sweep).Success, 0)
  return <LcarsLayout>
    <section className="panel-card panel-card-accent">
      <div className="panel-heading-row"><div><p className="lcars-eyebrow">Runs console</p><h1>Experiments</h1></div>
        <Link className="action-button" to="/experiment/new">+ Create experiment</Link></div>
      <p className="lead-copy">Create an experiment, follow its progress, and inspect the results. Try multiple parameter combinations when you need to compare configurations.</p>
    </section>
    <SweepNotice />
    <section className="metric-grid" aria-label="Experiment overview">
      {[[sweeps.length, 'Experiments'], [active, 'Active experiments'], [totalRuns, 'Runs'], [successful, 'Successful runs']].map(([value, label]) => <div className="metric-card" key={label}><span className="metric-label">{label}</span><strong className="metric-value">{String(value).padStart(2, '0')}</strong></div>)}
    </section>
    <section className="panel-card">
      <div className="panel-heading-row"><div><p className="lcars-eyebrow">Experiment library</p><h2>Your experiments</h2></div>
        <label className="field field-compact"><span className="sr-only">Search experiments</span><input type="search" placeholder="Search experiments" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div>
      {loading ? <p className="message-banner" role="status">Loading saved experiments…</p> : filtered.length ? <div className="sweep-catalog">{filtered.map((sweep) => <article className="sweep-catalog-item" key={sweep.id}>
        <div className="panel-heading-row"><div><Link to={`/experiment/${sweep.id}`} className="sweep-title-link">{sweep.name}</Link><p className="resource-meta">{sweep.algorithm.name} · {sweep.dataset.name}</p></div><StatusBadge status={sweepStatus(sweep)} /></div>
        <SweepProgress sweep={sweep} />
        <div className="sweep-card-footer"><span>{sweep.experiments.length} {sweep.experiments.length === 1 ? 'run' : 'runs'} · {new Date(sweep.created_at).toLocaleString()}</span><Link className="action-button secondary tiny" to={`/experiment/${sweep.id}`}>Inspect experiment →</Link></div>
      </article>)}</div> : <div className="empty-state sweep-empty">
        <span className="sweep-empty-symbol" aria-hidden="true">×</span>
        <h3>{sweeps.length ? 'No matching experiments' : 'No current experiments'}</h3>
        <p>{sweeps.length ? 'Try a different name, algorithm, dataset, or status.' : 'Choose an algorithm and dataset, configure your parameters, and launch your experiment.'}</p>
        {!sweeps.length ? <Link className="action-button" to="/experiment/new">Create your first experiment</Link> : null}
      </div>}
    </section>
  </LcarsLayout>
}
