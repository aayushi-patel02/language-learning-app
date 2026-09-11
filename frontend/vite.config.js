import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // Tailwind v4 is a Vite plugin. There is no tailwind.config.js and no
  // postcss config - configuration lives in src/index.css via @theme.
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy /api to Django in development so the browser sees one origin and
    // CORS never enters the picture locally. Production uses VITE_API_URL.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
