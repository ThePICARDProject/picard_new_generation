import { Navigate, Route, Routes } from 'react-router-dom'
import Landing from './pages/Landing'
import Submit from './pages/Submit'
import Experiments from './pages/Experiments'
import Profile from './pages/Profile'
import About from './pages/About'
import Sweeps from './pages/Sweeps'
import SweepCreate from './pages/SweepCreate'
import SweepDetail from './pages/SweepDetail'
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
      <Route path="/sweeps" element={<RequireAuth><Sweeps /></RequireAuth>} />
      <Route path="/sweeps/new" element={<RequireAuth><SweepCreate /></RequireAuth>} />
      <Route path="/sweeps/:id" element={<RequireAuth><SweepDetail /></RequireAuth>} />
      {/* Earlier links used /experiment/...; keep them working. */}
      <Route path="/experiment/new" element={<Navigate to="/sweeps/new" replace />} />
      <Route path="/experiment/:id" element={<RequireAuth><SweepDetail /></RequireAuth>} />
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
          <RequireAuth>
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
