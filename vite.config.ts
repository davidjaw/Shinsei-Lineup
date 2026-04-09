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
          ['-c', 'python3 script/build_frontend_data.py && python3 script/check_data_integrity.py'],
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

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    viteSingleFile(),
    rebuildDataShortcut(),
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
      external: ['vue', 'element-plus', '@element-plus/icons-vue'],
      output: {
        manualChunks: undefined,
        globals: {
          vue: 'Vue',
          'element-plus': 'ElementPlus',
          '@element-plus/icons-vue': 'ElementPlusIconsVue'
        }
      }
    }
  }
})
