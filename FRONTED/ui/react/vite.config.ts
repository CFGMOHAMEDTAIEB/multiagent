import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/files': 'http://127.0.0.1:8000', '/services': 'http://127.0.0.1:8000', '/agents': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' } },
  build: { outDir: '../../web-react', emptyOutDir: true },
})

