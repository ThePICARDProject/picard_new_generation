import { Navigate, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing'
import Submit from './pages/Submit'
import Experiments from './pages/Experiments'
import Profile from './pages/Profile'
import About from './pages/About'
import Sweeps from './pages/Sweeps'
import SweepCreate from './pages/SweepCreate'
import SweepDetail from './pages/SweepDetail'
import { SWEEPS_DEMO_MODE } from './features/sweeps/config'
import { useAuth } from './components/auth/AuthProvider'

function RequireAuth({ children }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <Landing />
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return children
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/about" element={<About />} />
      <Route path="/experiment/new" element={SWEEPS_DEMO_MODE ? <SweepCreate /> : <RequireAuth><SweepCreate /></RequireAuth>} />
      <Route path="/experiment/:id" element={SWEEPS_DEMO_MODE ? <SweepDetail /> : <RequireAuth><SweepDetail /></RequireAuth>} />
      <Route path="/sweeps" element={SWEEPS_DEMO_MODE ? <Sweeps /> : <RequireAuth><Sweeps /></RequireAuth>} />
      <Route path="/sweeps/new" element={SWEEPS_DEMO_MODE ? <SweepCreate /> : <RequireAuth><SweepCreate /></RequireAuth>} />
      <Route path="/sweeps/:id" element={SWEEPS_DEMO_MODE ? <SweepDetail /> : <RequireAuth><SweepDetail /></RequireAuth>} />
      <Route
        path="/submit"
        element={
          <RequireAuth>
            <Submit />
          </RequireAuth>
        }
      />
      <Route
        path="/experiments"
        element={
          SWEEPS_DEMO_MODE ? <Sweeps /> : <RequireAuth>
            <Experiments />
          </RequireAuth>
        }
      />
      <Route
        path="/profile"
        element={
          <RequireAuth>
            <Profile />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
