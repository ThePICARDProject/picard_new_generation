import { useState } from 'react'
import { Link } from 'react-router-dom'
import LcarsLayout from '../components/layout/LcarsLayout'
import StatusBadge from '../components/common/StatusBadge'
import { useSweeps } from '../features/sweeps/SweepContext'
import { SweepNotice, SweepProgress } from '../features/sweeps/SweepShared'
import { isActive } from '../features/sweeps/sweepApi'
import { sweepCounts, sweepStatus } from '../features/sweeps/sweepModel'
import { usePolling } from '../features/sweeps/usePolling'
import '../features/sweeps/sweeps.css'

export default function Sweeps() {
  const { sweeps, loading, repository } = useSweeps()
  const [search, setSearch] = useState('')
  const filtered = sweeps.filter((sweep) => `${sweep.name} ${sweep.algorithm.name} ${sweep.dataset.name} ${sweepStatus(sweep)}`.toLowerCase().includes(search.trim().toLowerCase()))
  const totalRuns = sweeps.reduce((sum, sweep) => sum + sweepCounts(sweep).total, 0)
  const active = sweeps.filter((sweep) => isActive(sweepStatus(sweep))).length
  const successful = sweeps.reduce((sum, sweep) => sum + sweepCounts(sweep).Success, 0)
  usePolling(() => repository.refresh(), active > 0)
  return <LcarsLayout>
    <section className="panel-card panel-card-accent">
      <div className="panel-heading-row"><div><p className="lcars-eyebrow">Sweep console</p><h1>Parameter sweeps</h1></div>
        <Link className="action-button" to="/sweeps/new">+ New sweep</Link></div>
      <p className="lead-copy">Run one algorithm on one dataset with several parameter combinations, follow progress, and download each run's results.</p>
    </section>
    <SweepNotice />
    <section className="metric-grid" aria-label="Sweep overview">
      {[[sweeps.length, 'Sweeps'], [active, 'Active sweeps'], [totalRuns, 'Runs'], [successful, 'Successful runs']].map(([value, label]) => <div className="metric-card" key={label}><span className="metric-label">{label}</span><strong className="metric-value">{String(value).padStart(2, '0')}</strong></div>)}
    </section>
    <section className="panel-card">
      <div className="panel-heading-row"><div><p className="lcars-eyebrow">Sweep library</p><h2>Your sweeps</h2></div>
        <label className="field field-compact"><span className="sr-only">Search sweeps</span><input type="search" placeholder="Search sweeps" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div>
      {loading ? <p className="message-banner" role="status">Loading sweeps…</p> : filtered.length ? <div className="sweep-catalog">{filtered.map((sweep) => <article className="sweep-catalog-item" key={sweep.id}>
        <div className="panel-heading-row"><div><Link to={`/sweeps/${sweep.id}`} className="sweep-title-link">{sweep.name}</Link><p className="resource-meta">{sweep.algorithm.name} · {sweep.dataset.name}</p></div><StatusBadge status={sweepStatus(sweep)} /></div>
        <SweepProgress sweep={sweep} />
        <div className="sweep-card-footer"><span>{sweep.total_count} {sweep.total_count === 1 ? 'run' : 'runs'} · {new Date(sweep.created_at).toLocaleString()}</span><Link className="action-button secondary tiny" to={`/sweeps/${sweep.id}`}>Inspect sweep →</Link></div>
      </article>)}</div> : <div className="empty-state sweep-empty">
        <span className="sweep-empty-symbol" aria-hidden="true">×</span>
        <h3>{sweeps.length ? 'No matching sweeps' : 'No sweeps yet'}</h3>
        <p>{sweeps.length ? 'Try a different name, algorithm, dataset, or status.' : 'Choose an algorithm and dataset, configure your parameters, and launch a sweep.'}</p>
        {!sweeps.length ? <Link className="action-button" to="/sweeps/new">Create your first sweep</Link> : null}
      </div>}
    </section>
  </LcarsLayout>
}
