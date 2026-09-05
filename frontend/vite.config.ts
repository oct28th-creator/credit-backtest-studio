import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // scripts/dev.sh exports VITE_API_PORT so a non-default API_PORT still
      // proxies correctly instead of silently 404ing into the demo fixtures.
      '/api': `http://localhost:${process.env.VITE_API_PORT ?? 8000}`
    }
  },
  build: {
    outDir: 'dist'
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['tests/unit/**/*.test.ts', 'src/**/*.test.ts'],
    exclude: ['tests/e2e/**'],
  }
})
