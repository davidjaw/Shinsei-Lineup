// Side-effect import: captures the raw window.location.hash at module-load
// time, BEFORE createRouter() below triggers vue-router's hash normalization
// (which prepends `/` and breaks our share/auth callback parsers). The order
// here is load-bearing — keep this import above createRouter().
// See src/lib/initial-hash.ts for the full explanation.
import '../lib/initial-hash'
import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import LineupBuilder from '../views/LineupBuilder.vue'

// Catch-all route is critical: legacy share links (#<base64>), short share links
// (#s/<slug>), and OAuth callbacks (#access_token=...) all hit the router with a
// non-`/` path. Sending them through LineupBuilder lets its onMounted handler
// consume the hash via initFromHash() before the URL is normalized to `#/`.
const routes: RouteRecordRaw[] = [
  { path: '/', component: LineupBuilder },
  { path: '/:pathMatch(.*)*', component: LineupBuilder },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
