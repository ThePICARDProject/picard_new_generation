import LcarsLayout from '../components/layout/LcarsLayout'
import StatusBadge from '../components/common/StatusBadge'
import { useAuth } from '../components/auth/AuthProvider'
import { useWorkspace } from '../components/workspace/WorkspaceProvider'

export default function Profile() {
  const { user } = useAuth()
  const { datasets, experiments, scripts, summary } = useWorkspace()

  const recentDatasets = datasets.slice(0, 3)
  const recentScripts = scripts.slice(0, 3)
  const recentExperiments = experiments.slice(0, 3)

  return (
    <LcarsLayout>
      <section className="panel-card panel-card-accent profile-hero">
        <div className="avatar-wrap">
          {user?.avatar_url ? <img src={user.avatar_url} alt="GitHub avatar" className="avatar-image" /> : <div className="avatar-fallback">{(user?.github_login || user?.username || 'P').slice(0, 1).toUpperCase()}</div>}
        </div>
        <div>
          <p className="lcars-eyebrow">Operator Profile</p>
          <h1>{user?.name || user?.github_login || user?.username || 'Unknown operator'}</h1>
          <p className="lead-copy">
            GitHub-backed session for PICARD resource management and experiment orchestration.
          </p>
          <div className="tag-list">
            <span className="access-pill public">{user?.github_login || user?.username || 'no-login'}</span>
            <span className="access-pill private">ThePICARDProject member</span>
          </div>
        </div>
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <span className="metric-label">Owned datasets</span>
          <strong className="metric-value">{summary.ownedDatasetCount}</strong>
          <p>{summary.datasetCount} visible total</p>
        </article>
        <article className="metric-card">
          <span className="metric-label">Owned algorithms</span>
          <strong className="metric-value">{summary.ownedScriptCount}</strong>
          <p>{summary.scriptCount} visible total</p>
        </article>
        <article className="metric-card">
          <span className="metric-label">Experiments</span>
          <strong className="metric-value">{summary.experimentCount}</strong>
          <p>{summary.activeCount} active</p>
        </article>
        <article className="metric-card">
          <span className="metric-label">Email</span>
          <strong className="metric-value metric-value-small">{user?.email || 'Not exposed by GitHub'}</strong>
          <p>Session-authenticated</p>
        </article>
      </section>

      <section className="panel-grid two-up">
        <article className="panel-card">
          <p className="lcars-eyebrow">Recent Assets</p>
          <h2>Latest datasets and algorithms</h2>
          <div className="split-list">
            <div>
              <h3>Datasets</h3>
              {recentDatasets.length ? (
                <ul className="simple-list">
                  {recentDatasets.map((dataset) => (
                    <li key={dataset.id}>{dataset.name}</li>
                  ))}
                </ul>
              ) : (
                <p className="empty-inline">No datasets uploaded yet.</p>
              )}
            </div>
            <div>
              <h3>Algorithms</h3>
              {recentScripts.length ? (
                <ul className="simple-list">
                  {recentScripts.map((script) => (
                    <li key={script.id}>{script.name}</li>
                  ))}
                </ul>
              ) : (
                <p className="empty-inline">No algorithms uploaded yet.</p>
              )}
            </div>
          </div>
        </article>

        <article className="panel-card">
          <p className="lcars-eyebrow">Recent Runs</p>
          <h2>Latest experiment identifiers</h2>
          {recentExperiments.length ? (
            <ul className="activity-list">
              {recentExperiments.map((experiment) => (
                <li key={experiment.id} className="activity-item">
                  <div>
                    <strong>Experiment #{experiment.id}</strong>
                    <p>{experiment.script_name}</p>
                  </div>
                  <StatusBadge status={experiment.status} />
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">No experiment history available yet.</div>
          )}

          {user?.profile_url ? (
            <div className="form-actions">
              <a className="action-button secondary" href={user.profile_url} rel="noreferrer" target="_blank">
                Open GitHub Profile
              </a>
            </div>
          ) : null}
        </article>
      </section>
    </LcarsLayout>
  )
}
