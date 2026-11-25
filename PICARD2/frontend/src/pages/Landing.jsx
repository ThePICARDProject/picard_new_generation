import { Link } from 'react-router-dom'
import LcarsLayout from '../components/layout/LcarsLayout'
import StatusBadge from '../components/common/StatusBadge'
import { useAuth } from '../components/auth/AuthProvider'
import { useSound } from '../components/audio/SoundProvider'
import { useWorkspace } from '../components/workspace/WorkspaceProvider'

export default function Landing() {
  const { isAuthenticated, isLoading, login, user } = useAuth()
  const { play } = useSound()
  const { experiments, summary } = useWorkspace()

  function startLogin() {
    play('confirm')
    window.setTimeout(() => {
      login()
    }, 90)
  }

  const recentExperiments = experiments.slice(0, 5)

  return (
    <LcarsLayout>
      <section className="panel-card panel-card-accent">
        <p className="lcars-eyebrow">Mission Control</p>
        <h1>PICARD command deck</h1>
        <p className="lead-copy">
          LCARS-styled operations for authenticated Spark experimentation. Manage CSV datasets,
          upload Python or JAR algorithms, queue runs, and inspect job output from a single console.
        </p>
        <div className="hero-actions">
          {isAuthenticated ? (
            <>
              <Link className="action-button" to="/submit">Open Submission Bay</Link>
              <Link className="action-button secondary" to="/experiments">Inspect Active Runs</Link>
            </>
          ) : (
            <>
              <button type="button" className="action-button" onClick={startLogin} disabled={isLoading}>
                Sign In With GitHub
              </button>
              <Link className="action-button secondary" to="/about">Read Platform Brief</Link>
            </>
          )}
        </div>
      </section>

      {isAuthenticated ? (
        <>
          <section className="metric-grid">
            <article className="metric-card">
              <span className="metric-label">Datasets</span>
              <strong className="metric-value">{summary.datasetCount}</strong>
              <p>{summary.publicDatasetCount} public</p>
            </article>
            <article className="metric-card">
              <span className="metric-label">Algorithms</span>
              <strong className="metric-value">{summary.scriptCount}</strong>
              <p>{summary.publicScriptCount} shared</p>
            </article>
            <article className="metric-card">
              <span className="metric-label">Experiments</span>
              <strong className="metric-value">{summary.experimentCount}</strong>
              <p>{summary.activeCount} active</p>
            </article>
            <article className="metric-card">
              <span className="metric-label">Operator</span>
              <strong className="metric-value metric-value-small">{user?.github_login || user?.username || 'unknown'}</strong>
              <p>ThePICARDProject verified</p>
            </article>
          </section>

          <section className="panel-grid two-up">
            <article className="panel-card">
              <p className="lcars-eyebrow">Recent Activity</p>
              <h2>Latest experiment runs</h2>
              {recentExperiments.length ? (
                <ul className="activity-list">
                  {recentExperiments.map((experiment) => (
                    <li key={experiment.id} className="activity-item">
                      <div>
                        <strong>{experiment.script_name}</strong>
                        <p>{experiment.dataset_name || 'No dataset attached'}</p>
                      </div>
                      <StatusBadge status={experiment.status} />
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="empty-state">
                  No experiments have been created yet. Start from the submission bay to build a run.
                </div>
              )}
            </article>

            <article className="panel-card">
              <p className="lcars-eyebrow">Workflow</p>
              <h2>Standard operating sequence</h2>
              <ul className="stack-list">
                <li>Upload or reuse a CSV dataset with private or public visibility.</li>
                <li>Upload a Python script or JAR, including the main class when required.</li>
                <li>Create an experiment from those assets, then queue or re-run it from the runs console.</li>
                <li>Review live logs and download saved result artifacts when Spark writes them.</li>
              </ul>
            </article>
          </section>
        </>
      ) : (
        <>
          <section className="panel-grid three-up" id="auth-access">
            <article className="panel-card">
              <p className="lcars-eyebrow">Authentication</p>
              <h2>GitHub only access</h2>
              <p>
                The frontend now relies on the Django session and GitHub OAuth flow instead of local storage
                tokens or placeholder login state.
              </p>
            </article>
            <article className="panel-card">
              <p className="lcars-eyebrow">Organization Gate</p>
              <h2>ThePICARDProject membership</h2>
              <p>
                The backend verifies organization membership after GitHub OAuth and rejects users outside
                ThePICARDProject.
              </p>
            </article>
            <article className="panel-card">
              <p className="lcars-eyebrow">Operations</p>
              <h2>What unlocks after sign-in</h2>
              <p>
                Submission controls, experiment orchestration, shared libraries, results inspection, and
                workspace summaries all become available after authentication.
              </p>
            </article>
          </section>

          <section className="panel-card" id="platform-stack">
            <p className="lcars-eyebrow">Platform Stack</p>
            <h2>Repository runtime path</h2>
            <ul className="stack-list">
              <li>Django provides session auth, upload endpoints, experiment state, and GitHub OAuth callbacks.</li>
              <li>Celery and Redis queue experiment execution while Spark runs submitted workloads.</li>
              <li>The LCARS frontend proxies backend traffic through the deployment origin for cleaner OAuth and cookie handling.</li>
              <li>Datasets stay CSV-only and algorithms stay limited to Python scripts and JAR uploads in this first pass.</li>
            </ul>
          </section>
        </>
      )}
    </LcarsLayout>
  )
}
