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
        <el-tooltip content="Discord：neko.vision（點擊複製）" placement="top" :show-after="200">
          <button type="button" class="footer-icon" @click="copyDiscord" aria-label="Discord">
            <el-icon :size="13"><ChatDotRound /></el-icon>
          </button>
        </el-tooltip>
        <a
          href="https://forms.gle/mnMAqAzP595ygCrJ9"
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

const copyDiscord = async () => {
  try {
    await navigator.clipboard.writeText('neko.vision')
    ElMessage.success('已複製 Discord：neko.vision')
  } catch {
    ElMessage.warning('無法存取剪貼簿，請手動複製：neko.vision')
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
