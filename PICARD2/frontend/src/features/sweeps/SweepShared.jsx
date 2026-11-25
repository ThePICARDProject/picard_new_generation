import { Link } from 'react-router-dom'
import { sweepCounts } from './sweepModel'
import { useSweeps } from './SweepContext'

export function SweepNotice() {
  const { error, repository } = useSweeps()
  return <>
    <div className="message-banner sweep-mode-banner">
      <span className="sweep-beacon" aria-hidden="true" />
      <div> <strong>Experiment execution is not connected</strong>
        <p>You can configure and preview experiments here.</p></div>
    </div>
    {error ? <div className="message-banner message-banner-error" role="alert">{error} <button type="button" className="action-button tiny secondary" onClick={() => repository.refresh()}>Retry storage</button></div> : null}
  </>
}

export function SweepProgress({ sweep }) {
  const counts = sweepCounts(sweep)
  return <div className="sweep-progress">
    <div className="sweep-progress-caption"><span>{counts.settled} / {counts.total} settled</span><strong>{counts.progress}%</strong></div>
    <div className="sweep-progress-track" role="progressbar" aria-label={`${sweep.name} progress`} aria-valuenow={counts.progress} aria-valuemin={0} aria-valuemax={100} aria-valuetext={`${counts.completed} completed, ${counts.Cancelled} cancelled, of ${counts.total}`}>
      {['Success', 'Failed', 'Cancelled', 'Running'].map((status) => <span key={status} className={`sweep-segment sweep-segment-${status.toLowerCase()}`} style={{ width: `${counts[status] / counts.total * 100}%` }} />)}
    </div>
    <p className="helper-text">{counts.Success} successful · {counts.Failed} failed · {counts.Cancelled} cancelled · {counts.Running} running · {counts.Queued + counts.Pending} waiting</p>
  </div>
}

export function SweepBackLink() {
  return <Link className="sweep-back-link" to="/experiments">← All experiments</Link>
}
