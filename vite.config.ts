import { defineConfig, type PluginOption, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'
import { spawn } from 'node:child_process'

// Press `d` in the dev terminal to re-run the Python data build and reload.
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
        server.config.logger.info('\n[data] rebuilding (build_frontend_data + check_data_integrity)...')
        const proc = spawn(
          'sh',
          ['-c', 'uv run script/build_frontend_data.py && uv run script/check_data_integrity.py'],
          { stdio: 'inherit' }
        )
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
    "script-src 'self' 'unsafe-inline' https://esm.sh",
    "style-src 'self' 'unsafe-inline' https://unpkg.com",
    "img-src 'self' data: https:",
    "connect-src 'self' https://esm.sh https://*.supabase.co",
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

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    viteSingleFile(),
    rebuildDataShortcut(),
    injectProdCsp(),
  ],
  resolve: {
    alias: {
      '@': '/src'
    }
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
