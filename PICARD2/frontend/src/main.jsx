import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './lcars-assets/classic.css'
import './index.css'
import App from './App.jsx'
import { SoundProvider } from './components/audio/SoundProvider'
import { AuthProvider } from './components/auth/AuthProvider'
import { WorkspaceProvider } from './components/workspace/WorkspaceProvider'
import SweepProvider from './features/sweeps/SweepProvider'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <SoundProvider>
        <AuthProvider>
          <WorkspaceProvider>
            <SweepProvider><App /></SweepProvider>
          </WorkspaceProvider>
        </AuthProvider>
      </SoundProvider>
    </BrowserRouter>
  </StrictMode>,
)
