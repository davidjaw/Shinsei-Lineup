import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Apart from vite.config.ts: its plugins serve the dev server and the single-file build.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
  },
})
