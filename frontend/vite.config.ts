import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, process.cwd(), '')
  const backendOrigin =
    process.env.BACKEND_ORIGIN ||
    environment.BACKEND_ORIGIN ||
    'http://127.0.0.1:8080'

  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      proxy: {
        '/actuator': { target: backendOrigin },
        '/api': { target: backendOrigin },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
  }
})
