<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    direction="ltr"
    size="300px"
    :with-header="false"
    class="!bg-white"
  >
    <div class="h-full bg-white text-ink flex flex-col">
      <header class="px-4 py-3 border-b border-divider">
        <h2 class="text-sm font-bold tracking-wide">配將模擬</h2>
      </header>

      <!-- Profile + Group selectors (moved from LineupHeader on mobile). -->
      <div class="px-3 py-2 border-b border-divider flex flex-col gap-2">
        <el-dropdown
          v-if="isLoggedIn"
          trigger="click"
          placement="bottom-start"
          @command="onProfileCommand"
          @visible-change="onProfileVisibleChange"
        >
          <button class="drawer-pill" type="button">
            <el-icon :size="13" class="opacity-70"><User /></el-icon>
            <span class="font-bold text-ink">角色</span>
            <span
              class="flex-1 font-bold truncate text-left"
              :class="activeProfileName ? 'text-focus' : 'text-ink-mute'"
            >{{ activeProfileName ?? '不使用' }}</span>
            <el-icon :size="12" class="opacity-60"><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu class="min-w-[240px]">
              <el-dropdown-item
                command="unload"
                :class="{ '!font-bold !text-focus': !activeProfileId }"
              >
                <el-icon class="mr-1"><CircleClose /></el-icon>
                <span>不使用（可用全部武將/戰法）</span>
              </el-dropdown-item>
              <el-dropdown-item
                v-for="p in profiles"
                :key="p.id"
                :command="`apply:${p.id}`"
                :class="{ '!font-bold !text-focus': activeProfileId === p.id }"
                divided
              >
                <el-icon class="mr-1" :class="p.is_default ? 'text-amber-500' : ''">
                  <component :is="p.is_default ? StarFilled : Avatar" />
                </el-icon>
                <span class="flex-1 truncate mr-2">{{ p.name }}</span>
                <span class="text-[11px] text-ink-mute tabular-nums">
                  {{ p.inv_h.length }}武 · {{ p.inv_s.length }}法
                </span>
              </el-dropdown-item>
              <el-dropdown-item command="edit-inventory" divided>
                <el-icon class="mr-1"><Edit /></el-icon> 編輯目前庫存…
              </el-dropdown-item>
              <el-dropdown-item command="goto-profiles">
                <el-icon class="mr-1"><Setting /></el-icon> 管理角色配置…
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-dropdown
          trigger="click"
          placement="bottom-start"
          @command="onGroupCommand"
        >
          <button class="drawer-pill" type="button">
            <span class="font-bold text-ink">編組</span>
            <span class="flex-1 font-bold text-focus truncate text-left">{{ currentGroup.name }}</span>
            <el-icon :size="12" class="opacity-60"><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu class="min-w-[200px]">
              <el-dropdown-item
                v-for="(g, idx) in groups"
                :key="g.id"
                :command="`switch:${idx}`"
                :class="{ '!font-bold !text-focus': idx === currentGroupIndex }"
              >
                <span class="text-xs text-ink-mute mr-1.5">{{ idx + 1 }}</span>
                {{ g.name }}
              </el-dropdown-item>
              <el-dropdown-item command="add" divided>
                <el-icon class="mr-1"><Plus /></el-icon> 新增編組
              </el-dropdown-item>
              <el-dropdown-item command="rename">
                <el-icon class="mr-1"><Edit /></el-icon> 重新命名
              </el-dropdown-item>
              <el-dropdown-item command="import-from-link">
                <el-icon class="mr-1"><Link /></el-icon> 由分享連結匯入…
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <div
          class="mode-pills"
          role="group"
          aria-label="配將模式"
        >
          <button
            type="button"
            class="mode-pill"
            :class="{ 'is-active': !showOwnedOnly }"
            :aria-pressed="!showOwnedOnly"
            @click="setCatalogMode(false)"
          >
            <el-icon :size="13"><Grid /></el-icon>
            自由模式
          </button>
          <button
            type="button"
            class="mode-pill"
            :class="{ 'is-active': showOwnedOnly }"
            :aria-pressed="showOwnedOnly"
            @click="setCatalogMode(true)"
          >
            <el-icon :size="13"><Box /></el-icon>
            庫存模式
          </button>
        </div>
      </div>

      <div class="flex-1 min-h-0 overflow-y-auto py-1">
        <div
          v-for="(team, idx) in lineups"
          :key="idx"
          role="button"
          tabindex="0"
          class="w-full flex items-center justify-between px-4 py-2 transition-colors text-left border-l-2 cursor-pointer"
          :class="currentTeamIndex === idx
            ? 'bg-highlight border-focus'
            : 'border-transparent hover:bg-highlight'"
          @click="$emit('select', idx)"
          @keydown.enter="$emit('select', idx)"
          @keydown.space.prevent="$emit('select', idx)"
        >
          <div class="flex items-center gap-2 min-w-0">
            <span class="text-xs text-ink-mute w-4 text-right">{{ idx + 1 }}</span>
            <span class="text-sm truncate">{{ team.name }}</span>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <span
              class="text-xs tabular-nums"
              :class="teamCost(team) > 20 ? 'text-red-500' : 'text-ink-mute'"
            >{{ teamCost(team) }}/20</span>
            <!-- Empty team → instant delete. Non-empty → popconfirm. Always
                 visible on mobile (no hover affordance). -->
            <span
              v-if="isEmptyTeam(team)"
              class="row-action"
              @click.stop="$emit('remove-team', idx)"
              @keydown.enter.stop="$emit('remove-team', idx)"
              @keydown.space.stop.prevent="$emit('remove-team', idx)"
              role="button"
              tabindex="0"
              :aria-label="`刪除 ${team.name}`"
            >
              <el-icon :size="14"><Delete /></el-icon>
            </span>
            <el-popconfirm
              v-else
              :title="`刪除「${team.name}」？無法復原`"
              confirm-button-text="刪除"
              cancel-button-text="取消"
              confirm-button-type="danger"
              :width="220"
              @confirm="$emit('remove-team', idx)"
            >
              <template #reference>
                <span
                  class="row-action"
                  @click.stop
                  role="button"
                  tabindex="0"
                  :aria-label="`刪除 ${team.name}`"
                >
                  <el-icon :size="14"><Delete /></el-icon>
                </span>
              </template>
            </el-popconfirm>
          </div>
        </div>

        <button
          v-if="lineups.length < MAX_TEAMS_PER_GROUP"
          type="button"
          class="w-full px-4 py-2 mt-1 text-left text-sm text-ink-mute hover:text-ink hover:bg-surface-muted transition-colors flex items-center gap-2 border-l-2 border-transparent"
          @click="$emit('add-team')"
        >
          <el-icon :size="14"><Plus /></el-icon>
          <span>新增配將</span>
        </button>
      </div>

      <div class="border-t border-divider px-3 py-3 flex flex-col gap-1.5">
        <button class="action-row" @click="$emit('compact')">
          <el-icon :size="14"><FullScreen /></el-icon>
          <span>截圖模式</span>
        </button>
        <button class="action-row" @click="$emit('share')">
          <el-icon :size="14"><Share /></el-icon>
          <span>分享</span>
        </button>
        <button class="action-row" @click="$emit('export-to-group')">
          <el-icon :size="14"><Position /></el-icon>
          <span>導出到其他編組</span>
        </button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Delete, Plus, Share, Position, User, ArrowDown, CircleClose,
  StarFilled, Avatar, Edit, Setting, Link, Grid, Box, FullScreen,
} from '@element-plus/icons-vue'
import { type Lineup, isEmptyTeam, computeTeamCost } from '../../composables/useLineups'
import { MAX_TEAMS_PER_GROUP } from '../../types/group'
import { useGroups } from '../../composables/useGroups'
import { useProfiles } from '../../composables/useProfiles'
import { useActiveProfile } from '../../composables/useActiveProfile'
import { useAuth } from '../../composables/useAuth'
import { useInventory } from '../../composables/useInventory'

defineProps<{
  modelValue: boolean
  lineups: Lineup[]
  currentTeamIndex: number
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'select', idx: number): void
  (e: 'remove-team', idx: number): void
  (e: 'add-team'): void
  (e: 'share'): void
  (e: 'export-to-group'): void
  (e: 'import-from-link'): void
  (e: 'compact'): void
}>()

const router = useRouter()
const { groups, currentGroup, currentGroupIndex, setCurrentGroup, addGroup, renameGroup } = useGroups()
const { profiles, refresh: refreshProfiles } = useProfiles()
const { activeProfileId, activeProfileName, applyProfile, unloadProfile } = useActiveProfile()
const { isLoggedIn } = useAuth()
const { isEditingInventory, startEditingInventory, showOwnedOnly, ownedHeroes, ownedSkills } = useInventory()

const teamCost = computeTeamCost

const setCatalogMode = (inventory: boolean) => {
  if (inventory === showOwnedOnly.value) return
  showOwnedOnly.value = inventory
  if (inventory && ownedHeroes.value.length === 0 && ownedSkills.value.length === 0) {
    ElMessage.info('庫存是空的，目前沒有可配置的武將／戰法')
  }
}

const onProfileVisibleChange = (visible: boolean) => {
  if (visible) void refreshProfiles().catch(() => { /* swallow */ })
}

const onProfileCommand = (cmd: string) => {
  if (isEditingInventory.value && (cmd === 'unload' || cmd.startsWith('apply:'))) {
    ElMessage.warning('請先儲存或取消庫存編輯')
    return
  }
  if (cmd === 'unload') {
    unloadProfile()
    ElMessage.info('已切換為不使用任何角色配置')
  } else if (cmd === 'edit-inventory') {
    startEditingInventory()
    emit('update:modelValue', false)
  } else if (cmd === 'goto-profiles') {
    router.push({ name: 'profiles' })
    emit('update:modelValue', false)
  } else if (cmd.startsWith('apply:')) {
    const id = cmd.slice(6)
    const p = profiles.value.find(x => x.id === id)
    if (!p) {
      ElMessage.error('找不到該角色配置，請重新整理頁面')
      return
    }
    applyProfile(p)
    ElMessage.success(`已套用「${p.name}」`)
  }
}

const onGroupCommand = async (cmd: string) => {
  if (cmd.startsWith('switch:')) {
    const idx = Number(cmd.slice(7))
    if (idx !== currentGroupIndex.value) setCurrentGroup(idx)
  } else if (cmd === 'add') {
    const newIdx = addGroup()
    setCurrentGroup(newIdx)
    ElMessage.success(`已建立並切換到 ${groups.value[newIdx].name}`)
  } else if (cmd === 'import-from-link') {
    emit('import-from-link')
  } else if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('輸入新名稱', '重新命名編組', {
        confirmButtonText: '儲存',
        cancelButtonText: '取消',
        inputValue: currentGroup.value.name,
        inputValidator: (v: string) => {
          const trimmed = (v ?? '').trim()
          if (!trimmed) return '名稱不可為空'
          if (trimmed.length > 20) return '名稱最多 20 字'
          return true
        },
      })
      const next = value.trim()
      if (next === currentGroup.value.name) return
      renameGroup(currentGroupIndex.value, next)
      ElMessage.success('編組已重新命名')
    } catch {
      // cancel = no-op
    }
  }
}
</script>

<style scoped>
.drawer-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 34px;
  padding: 0 10px;
  border-radius: 2px;
  background: rgb(var(--color-surface-muted));
  border: 1px solid rgb(var(--color-divider));
  color: #1F2937;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
  line-height: 1;
  box-sizing: border-box;
}
.drawer-pill:hover {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
}
.drawer-pill:focus-visible {
  outline: 2px solid rgb(var(--color-focus));
  outline-offset: 2px;
}

.mode-pills {
  display: inline-flex;
  width: 100%;
  flex-shrink: 0;
  align-items: center;
  gap: 2px;
  height: 34px;
  padding: 2px;
  border-radius: 2px;
  background: rgb(var(--color-surface-muted));
  border: 1px solid rgb(var(--color-divider));
  box-sizing: border-box;
}
.mode-pill {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 28px;
  padding: 0 8px;
  border: none;
  border-radius: 2px;
  background: transparent;
  color: #6B7280;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
  white-space: nowrap;
}
.mode-pill.is-active {
  background: rgb(var(--color-highlight));
  color: rgb(var(--color-focus));
}
.mode-pill:focus-visible {
  outline: 2px solid rgb(var(--color-focus));
  outline-offset: 2px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: #475569;
  background: transparent;
  border: 1px solid transparent;
  transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
  text-align: left;
  cursor: pointer;
}
.action-row:hover {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
  color: #1F2937;
}

.row-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  color: #94a3b8;
  cursor: pointer;
  transition: color 0.12s ease, background 0.12s ease;
}
.row-action:hover, .row-action:focus {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  outline: none;
}
</style>
