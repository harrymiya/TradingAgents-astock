import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/screening': {
        target: 'http://localhost:8788',
        changeOrigin: true,
      },
      '/api/analyze_status': {
        target: 'http://localhost:8788',
        changeOrigin: true,
      },
      '/api/analyze_stock': {
        target: 'http://localhost:8788',
        changeOrigin: true,
      },
      '/api/analyze': {
        target: 'http://localhost:8787',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/analyze/, '/analyze'),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        format: 'iife',
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
        inlineDynamicImports: true,
      },
    },
  },
})
