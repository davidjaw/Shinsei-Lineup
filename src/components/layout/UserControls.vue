<template>
  <div class="flex items-center gap-1">
    <el-button text class="help-btn !rounded-sm !px-2" title="更新紀錄" @click="$emit('open-changelog')">
      <el-icon><Bell /></el-icon>
      <span v-if="hasUnseenChangelog" class="help-btn-dot" />
    </el-button>

    <template v-if="!isLoggedIn">
      <el-button text @click="$emit('open-auth')" class="hidden sm:inline-flex !rounded-sm">
        <el-icon class="mr-1"><User /></el-icon> 登入
      </el-button>
      <el-button text @click="$emit('open-auth')" class="sm:hidden !rounded-sm !px-2">
        <el-icon><User /></el-icon>
      </el-button>
    </template>
    <el-dropdown
      v-else
      trigger="click"
      @command="(cmd: UserMenuCmd) => $emit('user-menu', cmd)"
      placement="bottom-end"
    >
      <button class="user-pill" type="button">
        <el-icon><User /></el-icon>
        <span class="hidden sm:inline user-pill-name">
          <UserTag :name="displayName || 'user'" :user-id="userId" />
        </span>
        <el-icon class="opacity-70"><ArrowDown /></el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu class="min-w-[220px]">
          <el-dropdown-item command="changelog">
            <el-icon class="mr-1"><Notebook /></el-icon>
            <span>更新紀錄</span>
            <span
              v-if="hasUnseenChangelog"
              class="ml-auto pl-2 text-[10px] font-bold text-emerald-600"
            >NEW</span>
          </el-dropdown-item>
          <el-dropdown-item command="rename" divided>
            <el-icon class="mr-1"><Edit /></el-icon> 編輯名稱
          </el-dropdown-item>
          <el-dropdown-item command="signout">
            <el-icon class="mr-1"><Close /></el-icon> 登出
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { Bell, User, ArrowDown, Notebook, Edit, Close } from '@element-plus/icons-vue'
import UserTag from '../UserTag.vue'

export type UserMenuCmd = 'changelog' | 'rename' | 'signout'

defineProps<{
  isLoggedIn: boolean
  displayName: string | null
  userId?: string | null
  hasUnseenChangelog: boolean
}>()

defineEmits<{
  (e: 'open-changelog'): void
  (e: 'open-auth'): void
  (e: 'user-menu', cmd: UserMenuCmd): void
}>()
</script>

<style scoped>
.user-pill {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  margin-left: 4px;
  border-radius: 2px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  color: #4338ca;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
  line-height: 1;
  box-sizing: border-box;
}
.user-pill-name {
  max-width: 180px;
  min-width: 0;
}
.user-pill:hover {
  background: #e0e7ff;
  border-color: #a5b4fc;
}
.user-pill:focus-visible {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
}
@media (max-width: 767px) {
  .user-pill {
    padding: 0 6px;
    gap: 2px;
  }
}
.help-btn {
  position: relative;
}
.help-btn-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #ef4444;
  box-shadow: 0 0 0 2px #ffffff;
  pointer-events: none;
}
</style>
