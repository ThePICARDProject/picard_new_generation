import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import StatusBadge from '../common/StatusBadge'
import { useAuth } from '../auth/AuthProvider'
import { useSound } from '../audio/SoundProvider'
import { useWorkspace } from '../workspace/WorkspaceProvider'
import { SWEEPS_DEMO_MODE } from '../../features/sweeps/config'
import { useSweeps } from '../../features/sweeps/SweepContext'

function padMetric(value, width = 4) {
  return String(value).padStart(width, '0')
}

function getPathCode(pathname) {
  if (pathname === '/') {
    return 'HOME'
  }

  return pathname.replace(/^\//, '').slice(0, 8).toUpperCase() || 'MAIN'
}

function buildTelemetryColumns({ isAuthenticated, pathname, summary, user }) {
  const now = new Date()
  const userLabel = user?.github_login || user?.username || 'guest'

  return [
    ['93', '1853', padMetric(summary.datasetCount, 5), padMetric(summary.scriptCount, 4), padMetric(summary.experimentCount, 5), padMetric(summary.activeCount, 3), getPathCode(pathname)],
    [padMetric(now.getUTCFullYear(), 4), padMetric(now.getUTCMonth() + 1, 2), padMetric(now.getUTCDate(), 2), padMetric(now.getUTCHours(), 2), padMetric(now.getUTCMinutes(), 2), padMetric(now.getUTCSeconds(), 2), 'UTC'],
    [userLabel.slice(0, 7).toUpperCase(), isAuthenticated ? 'AUTH' : 'GUEST', isAuthenticated ? 'LIVE' : 'LOCK', 'ORG', 'PICARD', 'LCARS', 'SYNC'],
    [padMetric(summary.ownedDatasetCount, 3), padMetric(summary.ownedScriptCount, 3), padMetric(summary.publicDatasetCount, 3), padMetric(summary.publicScriptCount, 3), padMetric(summary.runningCount, 3), padMetric(summary.queuedCount, 3), 'READY'],
    ['7024', '4149', '86', '05', '2048', '3198', '4623'],
    ['0223', '688', '28471', '21366', '8654', '31', '1984'],
    ['72112', '101088', '604122', '126523', '86801', 'LV426', '220655'],
    ['80106', '1314577', '39001', '7162893', '12855', '57', '6244009'],
  ]
}

export default function LcarsLayout({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { authError, isAuthenticated, login, logout, user } = useAuth()
  const { isRefreshing, summary: workspaceSummary, workspaceError } = useWorkspace()
  const { sweeps, algorithms, datasets } = useSweeps()
  const summary = useMemo(() => {
    if (!SWEEPS_DEMO_MODE) return workspaceSummary
    const runs = sweeps.flatMap((sweep) => sweep.experiments)
    return { ...workspaceSummary, datasetCount: datasets.length, scriptCount: algorithms.length,
      experimentCount: runs.length, activeCount: runs.filter((run) => ['Pending', 'Queued', 'Running'].includes(run.status)).length,
      runningCount: runs.filter((run) => run.status === 'Running').length,
      queuedCount: runs.filter((run) => run.status === 'Queued').length }
  }, [sweeps, algorithms, datasets, workspaceSummary])
  const { play, soundEnabled, toggleSound } = useSound()
  const [showTopButton, setShowTopButton] = useState(false)

  useEffect(() => {
    function onScroll() {
      setShowTopButton(window.scrollY > 180)
    }

    onScroll()
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const navigationItems = useMemo(() => {
    if (isAuthenticated) {
      return [
        { label: 'HOME', to: '/' },
        { label: 'SUBMIT', to: '/submit' },
        { label: 'EXPERIMENTS', to: '/experiments' },
        { label: 'PROFILE', to: '/profile' },
      ]
    }

    if (SWEEPS_DEMO_MODE) return [
      { label: 'HOME', to: '/' },
      { label: 'EXPERIMENTS', to: '/experiments' },
      { label: 'NEW EXPERIMENT', to: '/experiment/new' },
      { label: 'ABOUT', to: '/about' },
    ]

    return [
      { label: 'SIGN IN', action: () => login() },
      { label: 'ABOUT', to: '/about' },
      { label: 'ACCESS', action: () => document.getElementById('auth-access')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) },
      { label: 'STACK', action: () => document.getElementById('platform-stack')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) },
    ]
  }, [isAuthenticated, login])

  const telemetryColumns = useMemo(() => {
    return buildTelemetryColumns({
      isAuthenticated,
      pathname: location.pathname,
      summary,
      user,
    })
  }, [isAuthenticated, location.pathname, summary, user])

  function triggerAction(action, soundName = 'nav') {
    play(soundName)
    window.setTimeout(() => {
      action()
    }, 90)
  }

  function handleNavigation(item) {
    if (item.to) {
      triggerAction(() => navigate(item.to))
      return
    }

    if (item.action) {
      triggerAction(item.action)
    }
  }

  function handleLogout() {
    triggerAction(() => {
      logout()
        .catch(() => undefined)
        .finally(() => navigate('/'))
    }, 'alert')
  }

  const sessionLabel = SWEEPS_DEMO_MODE ? 'Authenticated' : isAuthenticated
    ? user?.name || user?.github_login || user?.username || 'Authenticated User'
    : 'GitHub authentication required'

  const shellStatus = workspaceError || authError

  return (
    <>
      <section className={`wrap-standard app-shell${SWEEPS_DEMO_MODE || location.pathname.startsWith('/sweeps') || location.pathname.startsWith('/experiment/') ? ' sweep-shell' : ''}`} id="column-3">
        <div className="wrap">
          <div className="left-frame-top">
            <button type="button" onClick={() => triggerAction(() => navigate('/'))} className="panel-1-button">
              LCARS
            </button>
            <div className="panel-2">P2<span className="hop">-042926</span></div>
          </div>
          <div className="right-frame-top">
            <div className="banner">
              PICARD LCARS • {SWEEPS_DEMO_MODE ? 'LOCAL DEMO' : isAuthenticated ? 'SESSION ACTIVE' : 'AUTH REQUIRED'}
            </div>
            <div className="data-cascade-button-group">
              <div className="data-cascade-wrapper" id="default" aria-hidden="true">
                {telemetryColumns.map((column, columnIndex) => (
                  <div key={`${columnIndex}-${column[0]}`} className="data-column">
                    {column.map((value, rowIndex) => (
                      <div key={`${columnIndex}-${rowIndex}`} className={`dc-row-${Math.min(rowIndex + 1, 7)}`}>
                        {value}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              <nav aria-label="Primary">
                {navigationItems.map((item) => {
                  const isActive = item.to === location.pathname || (item.to === '/experiments' && ((location.pathname.startsWith('/experiment/') && location.pathname !== '/experiment/new') || location.pathname.startsWith('/sweeps')))
                  return (
                    <button
                      key={item.label}
                      type="button"
                      onClick={() => handleNavigation(item)}
                      className={isActive ? 'lcars-nav-current' : ''}
                      aria-current={isActive ? 'page' : undefined}
                    >
                      {item.label}
                    </button>
                  )
                })}
              </nav>
            </div>
            <div className="bar-panel first-bar-panel">
              <div className="bar-1"></div>
              <div className="bar-2"></div>
              <div className="bar-3"></div>
              <div className="bar-4"></div>
              <div className="bar-5"></div>
            </div>
          </div>
        </div>
        <div className="wrap" id="gap">
          <div className="left-frame">
            <button
              type="button"
              onClick={() => triggerAction(() => window.scrollTo({ top: 0, behavior: 'smooth' }), 'soft')}
              id="topBtn"
              style={{ display: showTopButton ? 'block' : 'none' }}
            >
              <span className="hop">screen</span> top
            </button>
            <div>
              <div className="panel-3 lcars-panel-stat"><span>mode</span><strong>{SWEEPS_DEMO_MODE ? 'demo' : isAuthenticated ? 'mission' : 'guest'}</strong></div>
              <div className="panel-4 lcars-panel-stat"><span>datasets</span><strong>{padMetric(summary.datasetCount, 2)}</strong></div>
              <div className="panel-5 lcars-panel-stat lcars-panel-compact"><span>scripts</span><strong>{padMetric(summary.scriptCount, 2)}</strong></div>
              <div className="panel-6 lcars-panel-stat"><span>runs</span><strong>{padMetric(summary.experimentCount, 2)}</strong></div>
              <div className="panel-7 lcars-panel-stat"><span>queue</span><strong>{padMetric(summary.activeCount, 2)}</strong></div>
              <div className="panel-8 lcars-panel-stat"><span>audio</span><strong>{soundEnabled ? 'on' : 'off'}</strong></div>
              <div className="panel-9 lcars-sidebar-panel">
                <p className="lcars-eyebrow">Session</p>
                <h3 className="lcars-sidebar-title">{sessionLabel}</h3>
                <p className="lcars-sidebar-copy">
                  {SWEEPS_DEMO_MODE ? 'Create experiments and compare results. Demo data stays in this browser and no Spark jobs are submitted.' : isAuthenticated
                    ? 'Use the command panels to upload assets, assemble experiments, and inspect Spark results.'
                    : 'Sign in with GitHub to access submission workflows, experiment runs, and personal resource libraries.'}
                </p>
                {isAuthenticated ? (
                  <div className="lcars-sidebar-status">
                    <StatusBadge status={summary.activeCount > 0 ? 'Running' : 'Success'} />
                    <span>{summary.activeCount > 0 ? `${summary.activeCount} active jobs` : 'No active jobs'}</span>
                  </div>
                ) : null}
                <div className="sidebar-nav">
                  <button type="button" onClick={() => triggerAction(() => toggleSound(), 'soft')}>
                    {soundEnabled ? 'Mute Audio' : 'Enable Audio'}
                  </button>
                  {SWEEPS_DEMO_MODE ? (
                    <button type="button" onClick={() => triggerAction(() => navigate('/experiments'))}>Open Experiments</button>
                  ) : isAuthenticated ? (
                    <button type="button" onClick={() => triggerAction(() => navigate('/about'))}>About</button>
                  ) : (
                    <button type="button" onClick={() => triggerAction(() => login())}>GitHub Sign In</button>
                  )}
                  {SWEEPS_DEMO_MODE ? (
                    <button type="button" onClick={() => triggerAction(() => navigate('/experiment/new'))}>Create Experiment</button>
                  ) : isAuthenticated ? (
                    <button type="button" onClick={() => triggerAction(() => navigate('/submit'))}>Open Submit</button>
                  ) : (
                    <button type="button" onClick={() => triggerAction(() => navigate('/about'))}>About PICARD</button>
                  )}
                  {SWEEPS_DEMO_MODE ? (
                    <button type="button" onClick={() => triggerAction(() => navigate('/about'))}>About PICARD</button>
                  ) : isAuthenticated ? (
                    <button type="button" onClick={handleLogout}>Sign Out</button>
                  ) : (
                    <button type="button" onClick={() => triggerAction(() => navigate('/about'))}>Access Policy</button>
                  )}
                </div>
              </div>
            </div>
            <div>
              <div className="panel-10 lcars-panel-stat lcars-panel-compact">
                <span>org</span>
                <strong>ThePICARDProject</strong>
              </div>
            </div>
          </div>
          <div className="right-frame">
            <div className="bar-panel">
              <div className="bar-6"></div>
              <div className="bar-7"></div>
              <div className="bar-8"></div>
              <div className="bar-9"></div>
              <div className="bar-10"></div>
            </div>
            <main>
              {shellStatus ? (
                <section className="message-banner message-banner-error" role="alert">
                  {shellStatus}
                </section>
              ) : null}
              {isRefreshing ? (
                <section className="message-banner" aria-live="polite">
                  Synchronizing workspace state...
                </section>
              ) : null}
              <div className="lcars-page-stack">{children}</div>
            </main>
            <footer>
              PICARD Spark operations console • GitHub OAuth routed through the deployment frontend origin.
              <br />
              LCARS Inspired Website Template by <a href="https://www.thelcars.com" rel="noreferrer" target="_blank">www.TheLCARS.com</a>.
            </footer>
          </div>
        </div>
      </section>
      <div className="headtrim"></div>
      <div className="baseboard"></div>
    </>
  )
}
