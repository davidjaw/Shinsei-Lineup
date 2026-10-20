import { defineConfig, type PluginOption, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'
import { spawn } from 'node:child_process'
import { statSync } from 'node:fs'
import type { IncomingMessage } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { fetchSialiaSnapshot, SNAPSHOT_ID_RE } from './src/lib/handbookSialia'


// Root-level files are watched; of the top-level folders only these are.
// data/ is not: the `d` shortcut below rebuilds .build/ from it explicitly.
const ROOT = path.dirname(fileURLToPath(import.meta.url))
const WATCHED_DIRS = new Set(['src', '.build', 'public'])

function isUnwatched(file: string): boolean {
  const rel = path.relative(ROOT, file)
  if (!rel || rel.startsWith('..') || path.isAbsolute(rel)) return false
  const top = rel.split(path.sep)[0]
  if (WATCHED_DIRS.has(top)) return false
  return top !== rel || !!statSync(file, { throwIfNoEntry: false })?.isDirectory()
}

// Press `d` in the dev terminal to re-run `npm run data` (the one data entry point) and reload.
// Avoids having to ctrl+c and `npm run dev` again after editing data/scripts.
function rebuildDataShortcut(): PluginOption {
  return {
    name: 'rebuild-data-shortcut',
    apply: 'serve',
    configureServer(server: ViteDevServer) {
      let running = false
      const rebuild = () => {
        if (running) {
          server.config.logger.info('[data] already rebuilding, skipped')
          return
        }
        running = true
        server.config.logger.info('\n[data] rebuilding (npm run data)...')
        const proc = spawn('npm', ['run', 'data'], { stdio: 'inherit' })
        proc.on('exit', (code) => {
          running = false
          if (code === 0) {
            server.config.logger.info('[data] rebuild ok → triggering full reload')
            server.ws.send({ type: 'full-reload', path: '*' })
          } else {
            server.config.logger.error(`[data] rebuild failed (exit ${code})`)
          }
        })
      }

      server.bindCLIShortcuts({
        print: true,
        customShortcuts: [
          {
            key: 'd',
            description: 'rebuild data (python) + reload',
            action: rebuild,
          },
        ],
      })
    },
  }
}

// CSP is injected only into the production build, not the Vite dev server,
// because dev needs HMR scripts/eval that prod doesn't. `frame-ancestors` is
// intentionally absent — it's ignored when delivered via <meta>; for real
// click-jacking protection set it as an HTTP header at the host instead.
function injectProdCsp(): PluginOption {
  const csp = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://esm.sh https://static.cloudflareinsights.com",
    "style-src 'self' 'unsafe-inline' https://unpkg.com",
    "img-src 'self' data: https:",
    "connect-src 'self' https://esm.sh https://*.supabase.co https://cloudflareinsights.com",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
  ].join('; ')
  return {
    name: 'inject-prod-csp',
    apply: 'build',
    transformIndexHtml(html) {
      const meta = `<meta http-equiv="Content-Security-Policy" content="${csp}">`
      return html.replace('<head>', `<head>\n    ${meta}`)
    },
  }
}

async function readJsonBody(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }
  const raw = Buffer.concat(chunks).toString('utf8').trim()
  if (!raw) return {}
  return JSON.parse(raw)
}



// Dev-only: browser cannot call Sialia (CORS). Prod uses the Supabase
// edge function `handbook-snapshot`.
function handbookSnapshotProxy(): PluginOption {
  return {
    name: 'handbook-snapshot-proxy',
    apply: 'serve',
    configureServer(server: ViteDevServer) {
      server.middlewares.use('/api/handbook-snapshot', (req, res) => {
        void (async () => {
          const send = (status: number, body: unknown) => {
            res.statusCode = status
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(body))
          }
          if (req.method === 'OPTIONS') {
            res.statusCode = 204
            res.end()
            return
          }
          if (req.method !== 'POST') {
            send(405, { error: 'method not allowed' })
            return
          }
          let snapshotId = ''
          try {
            const body = (await readJsonBody(req)) as { snapshot_id?: unknown }
            snapshotId = typeof body.snapshot_id === 'string' ? body.snapshot_id.trim() : ''
          } catch {
            send(400, { error: 'invalid json' })
            return
          }
          if (!SNAPSHOT_ID_RE.test(snapshotId)) {
            send(400, { error: '無效的 snapshot_id' })
            return
          }
          try {
            const snap = await fetchSialiaSnapshot(snapshotId)
            send(200, snap)
          } catch (e) {
            send(502, { error: e instanceof Error ? e.message : '無法連線官方圖鑑' })
          }
        })()
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    viteSingleFile(),
    rebuildDataShortcut(),
    handbookSnapshotProxy(),

    injectProdCsp(),
  ],
  resolve: {
    alias: {
      '@': '/src'
    }
  },
  // Watch only what the app is built from. A local checkout can hold large
  // untracked folders next to src/; walking them (or scanning their .html as
  // dep entries) hangs the dev server until it runs out of memory.
  server: {
    watch: { ignored: isUnwatched },
  },
  optimizeDeps: {
    entries: ['index.html'],
  },
  build: {
    target: 'esnext',
    assetsInlineLimit: 100000000, // Try to inline everything
    chunkSizeWarningLimit: 100000000,
    cssCodeSplit: false,
    rollupOptions: {
      // Externalize Vue to use from CDN
      external: ['vue', 'vue-router', 'element-plus', '@element-plus/icons-vue'],
      output: {
        manualChunks: undefined,
        globals: {
          vue: 'Vue',
          'vue-router': 'VueRouter',
          'element-plus': 'ElementPlus',
          '@element-plus/icons-vue': 'ElementPlusIconsVue'
        }
      }
    }
  }
})
