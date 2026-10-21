import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command, mode }) => {
  const config = {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
  }

  if (command === 'serve') {
    const backendEnv = loadEnv(mode, path.resolve(__dirname, '../backend'), '')
    const backendLocalUrl = backendEnv.BACKEND_LOCAL_URL?.trim()

    if (!backendLocalUrl) {
      throw new Error('BACKEND_LOCAL_URL must be set in backend/.env or the environment.')
    }

    config.server = {
      fs: {
        allow: [path.resolve(__dirname, '..')],
      },
      host: '0.0.0.0',
      proxy: {
        '/auth/': { target: backendLocalUrl, changeOrigin: true },
        '/datasets/': { target: backendLocalUrl, changeOrigin: true },
        '/scripts/': { target: backendLocalUrl, changeOrigin: true },
        '/experiments/': { target: backendLocalUrl, changeOrigin: true },
        '/media/': { target: backendLocalUrl, changeOrigin: true },
      },
    }
  }

  return config
})
