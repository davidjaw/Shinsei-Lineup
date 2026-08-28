// Side-effect import: captures the raw window.location.hash at module-load
// time, BEFORE createRouter() below triggers vue-router's hash normalization
// (which prepends `/` and breaks our share/auth callback parsers). The order
// here is load-bearing — keep this import above createRouter().
// See src/lib/initial-hash.ts for the full explanation.
import '../lib/initial-hash'
import { peekInitialHash } from '../lib/initial-hash'
import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'
import LineupBuilder from '../views/LineupBuilder.vue'
import ProfilesView from '../views/ProfilesView.vue'
import MyGroups from '../views/MyGroups.vue'
import SharesView from '../views/SharesView.vue'
import ProposalsView from '../views/ProposalsView.vue'
import GachaLogPage from '../views/GachaLogPage.vue'
import SettingsView from '../views/SettingsView.vue'
import ComingSoon from '../views/ComingSoon.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'lineup', component: LineupBuilder },
      {
        path: 'profiles',
        name: 'profiles',
        component: ProfilesView,
        meta: {
          title: '角色管理',
          description: '每個角色配置是一份具名的庫存（武將 + 戰法）。可建立多份用於主帳 / 小號 / 朋友的庫存，套用後配將模擬會以該庫存為準。',
        },
      },
      {
        path: 'groups',
        name: 'groups',
        component: MyGroups,
        meta: {
          title: '我的編組',
          // Cap mirrors MAX_TEAMS_PER_GROUP in types/group.ts — update both if changed.
          description: '每個編組可放最多 10 支隊伍。自由模式與庫存模式的編組分開保存，此頁只顯示目前模式。',
        },
      },
      {
        path: 'shares',
        name: 'shares',
        component: SharesView,
        meta: {
          title: '我的分享',
          description: '所有已建立的分享連結。可釘選到頂端、命名、複製連結、刪除。',
        },
      },
      {
        path: 'proposals',
        name: 'proposals',
        component: ProposalsView,
        meta: {
          title: '精選隊伍',
          description: '玩家公開分享的單隊提案。可投票、加入自己的編組，或檢視預覽。',
        },
      },
      {
        path: 'gacha-log',
        name: 'gachaLog',
        component: GachaLogPage,
        meta: {
          title: '抽卡紀錄',
          description: '為每個祈願池逐抽記錄，自動計算保底進度與稀有間隔；可分享給朋友檢視。',
        },
      },
      {
        path: 'settings',
        name: 'settings',
        component: SettingsView,
        meta: { title: '設定', description: '語系、外觀、帳號設定。' },
      },
      {
        path: 'coming-soon/:topic?',
        name: 'comingSoon',
        component: ComingSoon,
        meta: { title: '即將推出' },
      },
    ],
  },
  // Catch-all is critical: legacy share links (#<base64>), short share links
  // (#s/<slug>), and OAuth callbacks (#access_token=...) all hit the router with
  // a non-`/` path. Send them through LineupBuilder (no layout) so its onMounted
  // handler consumes the hash via initFromHash() before the URL is normalized
  // to `#/`.
  //
  // Guard differentiates real shares from typed garbage paths by inspecting
  // the captured hash: real shares come in as `#abc...` (no leading `/`),
  // while typed-by-hand URLs like `/#/foo` capture as `#/foo`. The latter
  // would otherwise leave the user on a chromeless LineupBuilder until F5,
  // since hash-only navigation doesn't re-fire onMounted to detect the
  // invalid blob. peek-not-consume so initFromHash can still process real
  // shares after the route mounts.
  {
    path: '/:pathMatch(.*)*',
    component: LineupBuilder,
    beforeEnter: () => {
      const raw = peekInitialHash()
      if (!raw || raw === '#' || raw.startsWith('#/')) {
        return { path: '/' }
      }
      return true
    },
  },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
