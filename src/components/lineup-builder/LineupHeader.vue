<template>
  <el-header class="app-header bg-white border-b border-divider flex items-center justify-between px-0 md:px-4 sticky top-0 z-50">
    <div class="flex items-center gap-1 md:gap-3 min-w-0 flex-1 overflow-hidden">
      <el-button class="md:hidden !px-1 !mr-0 flex-shrink-0" text @click="$emit('open-mobile-sidebar')">
        <el-icon :size="20"><Menu /></el-icon>
      </el-button>

      <!-- Profile selector — dropdown of the user's character profiles.
           Only shown when logged in; anonymous users have no profile concept
           and edit inventory directly via the right-side button.
           Mobile hides this; the MobileTeamDrawer renders an equivalent. -->
      <el-dropdown
        v-if="!isEditingInventory && !isCompactView && isLoggedIn"
        trigger="click"
        @command="onProfileCommand"
        @visible-change="onProfileVisibleChange"
        placement="bottom-start"
        class="hidden md:inline-flex"
      >
        <button class="profile-pill group-pill" type="button">
          <el-icon :size="13" class="opacity-70"><User /></el-icon>
          <span class="font-bold text-ink">角色</span>
          <span
            class="font-bold truncate max-w-[100px]"
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

      <!-- Group selector — dropdown with current group name. Switch is wired;
           rename / delete defer to a later follow-up.
           Mobile hides this; the MobileTeamDrawer renders an equivalent. -->
      <el-dropdown
        v-if="!isEditingInventory"
        trigger="click"
        @command="onGroupCommand"
        placement="bottom-start"
        class="hidden md:inline-flex"
      >
        <button class="group-pill" type="button">
          <span class="font-bold text-ink">編組</span>
          <span class="font-bold text-focus truncate max-w-[100px]">{{ currentGroup.name }}</span>
          <el-icon :size="12" class="opacity-60"><ArrowDown /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu class="min-w-[180px]">
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

      <div v-if="!isEditingInventory && !isCompactView" class="min-w-0 flex-1 sm:flex-none sm:w-48 flex items-center">
        <el-input
          :model-value="teamName"
          @update:model-value="(v: string) => $emit('update:teamName', v)"
          placeholder="輸入隊伍名稱"
          class="w-full min-w-0 font-bold"
          size="default"
        >
          <template #suffix>
            <el-icon class="el-input__icon"><Edit /></el-icon>
          </template>
        </el-input>
      </div>
      <div v-else-if="isEditingInventory" class="font-bold text-gray-800 text-lg">
        庫存編輯模式
      </div>

      <div v-if="!isEditingInventory && !isCompactView" class="text-xs font-bold bg-gray-100 px-3 py-1.5 rounded-sm border border-gray-200 flex items-center hidden sm:flex">
        <span class="text-gray-500 mr-1">Cost:</span>
        <span :class="{ 'text-red-500': totalCost > 20, 'text-gray-800': totalCost <= 20 }" class="text-sm">{{ totalCost }}/20</span>
      </div>
      <div v-if="!isEditingInventory && !isCompactView" class="text-xs font-bold bg-gray-100 px-2 py-1 rounded-sm border border-gray-200 items-center gap-1 hidden sm:flex">
        <span class="text-gray-500 mr-0.5">兵:</span>
        <span
          v-for="tt in TROOP_TYPES"
          :key="tt"
          class="px-1 rounded-sm"
          :class="troopLevels[tt] > 0 ? 'text-focus bg-highlight' : 'text-gray-400'"
        >{{ TROOP_LABELS[tt] }}{{ troopLevels[tt] }}</span>
      </div>
    </div>

    <div class="flex items-center gap-1 md:gap-1 pr-1 md:pr-0 flex-shrink-0">
      <template v-if="!isEditingInventory">
        <!-- Anonymous fallback: no profile pill exists for them, so keep an
             explicit 編輯庫存 button. Logged-in users access editing via the
             profile dropdown's 編輯目前庫存…項. Hidden in compact view. -->
        <template v-if="!isLoggedIn && !isCompactView">
          <el-button type="info" plain @click="$emit('start-editing-inventory')" class="hidden sm:inline-flex !rounded-sm">
            <el-icon class="mr-1"><Edit /></el-icon> 編輯庫存
          </el-button>
          <el-button type="info" plain @click="$emit('start-editing-inventory')" class="sm:hidden !rounded-sm !w-9 !h-9 !p-0">
            <el-icon><Edit /></el-icon>
          </el-button>
        </template>

        <template v-if="isCompactView">
          <el-button type="primary" plain @click="exitCompactView" class="hidden sm:inline-flex !rounded-sm">
            <el-icon class="mr-1"><Back /></el-icon> 返回編輯
          </el-button>
          <el-button type="primary" plain @click="exitCompactView" class="sm:hidden !rounded-sm !w-9 !h-9 !p-0" title="返回編輯">
            <el-icon><Back /></el-icon>
          </el-button>
        </template>

        <el-button type="primary" plain @click="$emit('open-share')" class="hidden sm:inline-flex !rounded-sm">
          <el-icon class="mr-1"><Share /></el-icon> 分享
        </el-button>
        <el-button type="primary" plain @click="$emit('open-share')" class="sm:hidden !rounded-sm !w-9 !h-9 !p-0">
          <el-icon><Share /></el-icon>
        </el-button>

        <template v-if="!isCompactView">
          <el-button type="danger" plain @click="$emit('open-reset')" class="hidden sm:inline-flex !rounded-sm">
            <el-icon class="mr-1"><Delete /></el-icon> 重置
          </el-button>
          <el-button type="danger" plain @click="$emit('open-reset')" class="sm:hidden !rounded-sm !w-9 !h-9 !p-0">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>

        <UserControls
          :is-logged-in="isLoggedIn"
          :display-name="displayName"
          :has-unseen-changelog="hasUnseenChangelog"
          @open-changelog="$emit('open-changelog')"
          @open-auth="$emit('open-auth')"
          @user-menu="(cmd) => $emit('user-menu', cmd)"
        />
      </template>
      <template v-else>
        <el-button @click="$emit('cancel-editing-inventory')" class="!rounded-sm">
          <el-icon class="mr-1"><Close /></el-icon> <span class="hidden sm:inline">取消</span>
        </el-button>

        <!-- Anonymous: single in-memory save button (preserves the no-login UX). -->
        <el-button
          v-if="!isLoggedIn"
          type="success"
          @click="$emit('save-inventory')"
          class="!rounded-sm"
        >
          <el-icon class="mr-1"><Check /></el-icon>
          <span class="hidden sm:inline">儲存（本次階段）</span>
        </el-button>

        <!-- Logged in: save to active profile (if any) -->
        <el-button
          v-if="isLoggedIn && activeProfileName"
          type="success"
          @click="$emit('save-inventory-active')"
          class="!rounded-sm"
        >
          <el-icon class="mr-1"><Check /></el-icon>
          <span class="hidden sm:inline">儲存到「{{ activeProfileName }}」</span>
          <span class="sm:hidden">儲存</span>
        </el-button>

        <!-- Logged in: save as new profile. Active state: separate inline input;
             no active state: this is the only save button (still input-driven). -->
        <div class="flex items-center gap-1 ml-1">
          <el-input
            v-if="isLoggedIn"
            v-model="newProfileName"
            size="default"
            maxlength="50"
            :placeholder="activeProfileName ? '另存為新庫存…' : '儲存為新庫存…'"
            class="!w-40 sm:!w-48"
            @keyup.enter="onSaveAsNew"
          />
          <el-button
            v-if="isLoggedIn"
            type="primary"
            :disabled="!newProfileName.trim()"
            @click="onSaveAsNew"
            class="!rounded-sm"
          >
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
      </template>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Edit, Share, Delete, Menu, User, ArrowDown, Close, Check, Plus, CircleClose, StarFilled, Avatar, Setting, Link, Back } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { TROOP_TYPES, TROOP_LABELS } from '../../constants/traits'
import type { TroopType } from '../../constants/traits'
import { useGroups } from '../../composables/useGroups'
import { useProfiles } from '../../composables/useProfiles'
import { useActiveProfile } from '../../composables/useActiveProfile'
import { useInventory } from '../../composables/useInventory'
import UserControls, { type UserMenuCmd } from '../layout/UserControls.vue'

const props = defineProps<{
  teamName: string
  totalCost: number
  troopLevels: Record<TroopType, number>
  isEditingInventory: boolean
  isLoggedIn: boolean
  hasUnseenChangelog: boolean
  displayName: string | null
  activeProfileName: string | null
}>()
const emit = defineEmits<{
  (e: 'update:teamName', v: string): void
  (e: 'open-mobile-sidebar'): void
  (e: 'start-editing-inventory'): void
  (e: 'cancel-editing-inventory'): void
  (e: 'save-inventory'): void
  (e: 'save-inventory-active'): void
  (e: 'save-inventory-new', name: string): void
  (e: 'open-share'): void
  (e: 'open-reset'): void
  (e: 'open-changelog'): void
  (e: 'open-auth'): void
  (e: 'user-menu', cmd: UserMenuCmd): void
  (e: 'apply-profile', id: string): void
  (e: 'unload-profile'): void
  (e: 'goto-profiles'): void
  (e: 'import-from-link'): void
}>()

const { groups, currentGroup, currentGroupIndex, setCurrentGroup, addGroup, renameGroup } = useGroups()
const { profiles, refresh: refreshProfiles } = useProfiles()
const { activeProfileId } = useActiveProfile()
const { isCompactView } = useInventory()

const exitCompactView = () => { isCompactView.value = false }

// Inline new-profile-name input shown alongside the save buttons during
// inventory editing. Reset each time the mode toggles so a stale draft from
// the previous session can't auto-submit when re-opened.
const newProfileName = ref('')
watch(() => props.isEditingInventory, () => { newProfileName.value = '' })

const onSaveAsNew = () => {
  const name = newProfileName.value.trim()
  if (!name) return
  emit('save-inventory-new', name)
}

const onProfileVisibleChange = (visible: boolean) => {
  // Refresh on open so the dropdown reflects rename/delete from another tab.
  // Errors are swallowed inside refresh's caller — silent fail is fine here.
  if (visible) void refreshProfiles().catch(() => { /* swallow */ })
}

const onProfileCommand = (cmd: string) => {
  if (cmd === 'unload') {
    emit('unload-profile')
  } else if (cmd === 'edit-inventory') {
    emit('start-editing-inventory')
  } else if (cmd === 'goto-profiles') {
    emit('goto-profiles')
  } else if (cmd.startsWith('apply:')) {
    emit('apply-profile', cmd.slice(6))
  }
}

const onGroupCommand = async (cmd: string) => {
  if (cmd.startsWith('switch:')) {
    const idx = Number(cmd.slice(7))
    if (idx !== currentGroupIndex.value) setCurrentGroup(idx)
  } else if (cmd === 'add') {
    const newIdx = addGroup()
    setCurrentGroup(newIdx)
    ElMessage.success(`已建立並切換到 ${groups[newIdx].name}`)
  } else if (cmd === 'import-from-link') {
    emit('import-from-link')
  } else if (cmd === 'rename') {
    // Inline prompt — same pattern as the rename buttons inside MyGroups.vue
    // and MyProfilesPanel.vue. Validates non-empty + length cap; ESC / cancel
    // is a soft no-op.
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
      // ElMessageBox rejects on cancel; treat as a no-op.
    }
  }
}
</script>

<style scoped>
.group-pill,
.profile-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
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
.group-pill:hover,
.profile-pill:hover {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
}
.group-pill:focus-visible,
.profile-pill:focus-visible {
  outline: 2px solid rgb(var(--color-focus));
  outline-offset: 2px;
}
</style>
