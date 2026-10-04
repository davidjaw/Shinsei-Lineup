<template>
  <div class="h-full flex flex-col py-3 px-2">
    <!-- Brand -->
    <RouterLink
      to="/"
      class="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-highlight"
      :class="collapsed && 'justify-center'"
      @click="$emit('nav')"
    >
      <div class="w-8 h-8 rounded-full border border-brand text-brand flex items-center justify-center font-brand font-bold text-[15.4px] leading-none shrink-0">猫</div>
      <div v-if="!collapsed" class="flex flex-col justify-center h-8 leading-none">
        <div class="font-brand font-bold text-ink text-[15.4px]">真戰配將</div>
        <div class="text-[11px] text-ink-mute tracking-wide mt-1">SHINSEI · v{{ latestVersion }}</div>
      </div>
    </RouterLink>

    <div class="mt-4 flex-1 overflow-y-auto">
      <!-- Owner's notice: buying accounts, contact over Discord -->
      <div
        class="mb-3 flex items-center gap-2 rounded-lg border border-brand/40 bg-brand/5"
        :class="collapsed ? 'justify-center p-1' : 'px-2.5 py-2'"
      >
        <div v-if="!collapsed" class="min-w-0 flex-1 leading-tight">
          <div class="text-[12px] font-bold text-ink">站長收滿紅帳號 <span class="text-brand">20w TWD</span></div>
          <div class="mt-0.5 text-[11px] text-ink-mute">請 DC 聯絡，點右側複製 ID</div>
        </div>
        <el-tooltip :content="collapsed ? `${BUY_NOTICE}，${DISCORD_HINT}` : DISCORD_HINT" :placement="collapsed ? 'right' : 'top'" :show-after="200">
          <button type="button" class="notice-dc" @click="copyDiscord" aria-label="複製 Discord ID">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path :d="DISCORD_ICON" /></svg>
          </button>
        </el-tooltip>
      </div>

      <SidebarSection v-if="!collapsed" label="主要功能" />
      <SidebarLink
        v-for="item in primaryNav"
        :key="item.catalogMode ?? item.name"
        :to="item.to"
        :icon="item.icon"
        :label="item.label"
        :badge="item.badge"
        :collapsed="collapsed"
        :active="isNavActive(item)"
        @click="onNavClick(item)"
      />

      <SidebarSection v-if="!collapsed" label="即將推出" class="mt-4" />
      <SidebarLink
        v-for="item in soonNav"
        :key="item.name"
        :to="item.to"
        :icon="item.icon"
        :label="item.label"
        badge="SOON"
        :collapsed="collapsed"
        :active="activeRoute === item.name"
        @click="$emit('nav')"
      />

      <SidebarSection v-if="!collapsed" label="八字沒半撇" class="mt-4" />
      <SidebarLink
        v-for="item in wishNav"
        :key="item.name"
        :to="item.to"
        :icon="item.icon"
        :label="item.label"
        badge="?"
        :collapsed="collapsed"
        :active="activeRoute === item.name"
        @click="$emit('nav')"
      />
    </div>

    <!-- Footer: contact panel above, settings/collapse below -->
    <div class="border-t border-divider pt-2 mt-2">
      <div v-if="!collapsed" class="px-1 mb-2 flex items-center gap-1">
        <el-tooltip content="yt.neko.vision@gmail.com" placement="top" :show-after="200">
          <a href="mailto:yt.neko.vision@gmail.com" class="footer-icon" aria-label="Email">
            <el-icon :size="13"><Message /></el-icon>
          </a>
        </el-tooltip>
        <el-tooltip :content="DISCORD_HINT" placement="top" :show-after="200">
          <button type="button" class="footer-icon" @click="copyDiscord" aria-label="Discord">
            <el-icon :size="13"><ChatDotRound /></el-icon>
          </button>
        </el-tooltip>
        <a
          href="https://forms.gle/7owhUXByanWwvSNH6"
          target="_blank"
          rel="noopener"
          class="footer-link"
        >
          <el-icon :size="12"><EditPen /></el-icon>
          <span>建議/回報</span>
        </a>
      </div>

      <SidebarLink
        :to="{ name: 'settings' }"
        :icon="Setting"
        label="設定"
        :collapsed="collapsed"
        :active="activeRoute === 'settings'"
        @click="$emit('nav')"
      />
      <button
        class="hidden md:flex w-full items-center gap-2 px-3 py-2 mt-1 rounded-lg text-ink-mute hover:bg-highlight text-xs"
        :class="collapsed && 'justify-center'"
        @click="$emit('toggle-collapse')"
      >
        <el-icon :size="14"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
        <span v-if="!collapsed">收合</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import {
  Grid, Box, Flag, Document, Aim, Reading, Setting, Fold, Expand,
  Message, ChatDotRound, EditPen, User, Share, MagicStick,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { LATEST_VERSION } from '../../constants/changelog'
import { useInventory } from '../../composables/useInventory'
import SidebarLink from './SidebarLink.vue'
import SidebarSection from './SidebarSection.vue'

const latestVersion = LATEST_VERSION

const props = defineProps<{ collapsed: boolean; activeRoute?: string }>()
const emit = defineEmits<{
  (e: 'nav'): void
  (e: 'toggle-collapse'): void
}>()

const { showOwnedOnly, ownedHeroes, ownedSkills } = useInventory()

const DISCORD_ID = 'neko.vision'
const DISCORD_HINT = `Discord：${DISCORD_ID}（點擊複製）`
const BUY_NOTICE = '站長收滿紅帳號 20w TWD'
// Discord logo (Simple Icons, 24x24 viewBox).
const DISCORD_ICON = 'M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z'

const copyDiscord = async () => {
  try {
    await navigator.clipboard.writeText(DISCORD_ID)
    ElMessage.success(`已複製 Discord：${DISCORD_ID}`)
  } catch {
    ElMessage.warning(`無法存取剪貼簿，請手動複製：${DISCORD_ID}`)
  }
}

type NavItem = {
  name: string
  to: RouteLocationRaw
  icon: Component
  label: string
  badge?: string
  catalogMode?: 'free' | 'inventory'
}

const isNavActive = (item: NavItem): boolean => {
  if (item.catalogMode === 'free') return props.activeRoute === 'lineup' && !showOwnedOnly.value
  if (item.catalogMode === 'inventory') return props.activeRoute === 'lineup' && !!showOwnedOnly.value
  return props.activeRoute === item.name
}

const onNavClick = (item: NavItem) => {
  if (item.catalogMode === 'free' || item.catalogMode === 'inventory') {
    const inventory = item.catalogMode === 'inventory'
    if (inventory !== showOwnedOnly.value) {
      showOwnedOnly.value = inventory
      if (inventory && ownedHeroes.value.length === 0 && ownedSkills.value.length === 0) {
        ElMessage.info('庫存是空的，目前沒有可配置的武將／戰法')
      }
    }
  }
  emit('nav')
}

const primaryNav: readonly NavItem[] = [
  { name: 'lineup', to: { name: 'lineup' }, icon: Grid, label: '自由模式', catalogMode: 'free' },
  { name: 'lineup', to: { name: 'lineup' }, icon: Box, label: '庫存模式', catalogMode: 'inventory' },
  { name: 'profiles', to: { name: 'profiles' }, icon: User, label: '角色管理' },
  { name: 'groups', to: { name: 'groups' }, icon: Flag, label: '我的編組' },
  { name: 'shares', to: { name: 'shares' }, icon: Share, label: '我的分享' },
  { name: 'proposals', to: { name: 'proposals' }, icon: Document, label: '精選隊伍' },
  { name: 'gachaLog', to: { name: 'gachaLog' }, icon: MagicStick, label: '抽卡紀錄' },
]

const soonNav: readonly NavItem[] = [
  { name: 'heroDb', to: { name: 'comingSoon', params: { topic: 'hero-db' } }, icon: Reading, label: '武將資料庫' },
]

// 八字沒半撇 — features that are nominally planned but realistically unlikely
// to ship. Kept reachable so curious users can still see the description page.
const wishNav: readonly NavItem[] = [
  { name: 'battleSim', to: { name: 'comingSoon', params: { topic: 'battle-sim' } }, icon: Aim, label: '戰鬥模擬' },
]
</script>

<style scoped>
.footer-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  border-radius: 6px;
  font-size: 11px;
  color: #94A3B8;
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.15s ease, background 0.15s ease;
}
.footer-link:hover {
  color: rgb(var(--color-focus));
  background: rgb(var(--color-highlight));
}

.notice-dc {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  color: #fff;
  background: #5865F2;
  border: none;
  cursor: pointer;
  transition: filter 0.15s ease;
}
.notice-dc:hover {
  filter: brightness(1.1);
}

.footer-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  color: #94A3B8;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}
.footer-icon:hover {
  color: rgb(var(--color-focus));
  background: rgb(var(--color-highlight));
}
</style>
