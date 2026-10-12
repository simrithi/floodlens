import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import type { Connect, Plugin } from 'vite'

const OUTPUTS_DIR = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '../data/outputs')
const TYPES: Record<string, string> = { '.json': 'application/json', '.jpg': 'image/jpeg', '.png': 'image/png' }

/**
 * Serves the backend pipeline results (data/outputs) at /analysis during dev and preview.
 * The images are third-party licensed and large, so they stay out of ui/public and out of git.
 * A deployed build points VITE_ANALYSIS_BASE at S3/CloudFront instead.
 */
function serveAnalysis(): Plugin {
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    const rel = decodeURIComponent((req.url ?? '/').split('?')[0])
    const file = path.join(OUTPUTS_DIR, rel)
    if (!file.startsWith(OUTPUTS_DIR + path.sep)) {
      res.statusCode = 403
      res.end()
      return
    }
    fs.stat(file, (err, stat) => {
      if (err || !stat.isFile()) return next()
      res.setHeader('Content-Type', TYPES[path.extname(file)] ?? 'application/octet-stream')
      res.setHeader('Cache-Control', 'no-cache')
      fs.createReadStream(file).pipe(res)
    })
  }
  return {
    name: 'floodlens-serve-analysis',
    configureServer: (server) => void server.middlewares.use('/analysis', handler),
    configurePreviewServer: (server) => void server.middlewares.use('/analysis', handler),
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // `npm run dev:demo` sets VITE_DEMO_PROXY (see .env.demo): /analysis is then proxied to the live
  // site's published results, so the app runs without data/ and without an AWS account.
  const demoProxy = loadEnv(mode, process.cwd(), '').VITE_DEMO_PROXY
  return {
    plugins: [react(), ...(demoProxy ? [] : [serveAnalysis()])],
    server: demoProxy ? { proxy: { '/analysis': { target: demoProxy, changeOrigin: true } } } : undefined,
    // MapLibre 6 loads its worker relative to its own module URL; pre-bundling breaks that path.
    optimizeDeps: { exclude: ['maplibre-gl'] },
  }
})
