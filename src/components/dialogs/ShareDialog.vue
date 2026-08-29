<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    title="分享配置"
    width="360px"
    align-center
  >
    <div class="flex flex-col gap-3">
      <div v-if="isLoggedIn" class="flex flex-col gap-1">
        <el-input
          :model-value="name"
          @update:model-value="(v: string) => $emit('update:name', v)"
          maxlength="50"
          placeholder="名稱（可選）"
          clearable
        />
        <p class="text-[11px] text-gray-400 leading-snug">
          此名稱僅顯示於「我的分享」列表，不會出現在分享連結或對方畫面
        </p>
      </div>

      <div
        v-if="isLoggedIn"
        class="flex items-start justify-between gap-3 rounded border border-divider bg-highlight/50 px-3 py-2"
      >
        <div class="flex flex-col gap-0.5 min-w-0">
          <span class="text-sm">
            以「<span class="font-bold"><UserTag :name="displayName || '我'" :user-id="userId" /></span> · <span class="font-bold">{{ groupName }}</span>」公開分享
          </span>
          <span class="text-[11px] text-ink-mute leading-snug">
            僅 <span class="font-bold">分享當前隊伍</span> 適用；勾選後會同時加入公開「精選隊伍」庫
          </span>
          <span v-if="isBanned" class="text-[11px] text-ink-mute leading-snug">
            此帳號已被封鎖，無法公開分享
          </span>
          <span v-else-if="asPublic" class="text-[11px] text-ink-mute leading-snug">
            勾選後，上方名稱會作為公開精選的隊伍名稱（空白則用編組·隊伍名）。
          </span>
        </div>
        <el-switch v-model="asPublic" :disabled="isBanned" class="flex-shrink-0 mt-0.5" />
      </div>

      <el-button type="primary" plain size="large" @click="$emit('share', { scope: 'all', asPublic: false })" class="w-full !m-0">
        <div class="flex flex-col items-center">
          <span class="font-bold">分享全部</span>
          <span class="text-xs opacity-80">所有隊伍 + 庫存 (備份用)</span>
        </div>
      </el-button>
      <el-button type="success" plain size="large" @click="$emit('share', { scope: 'current', asPublic: asPublic && !isBanned })" class="w-full !m-0">
        <div class="flex flex-col items-center">
          <span class="font-bold">分享當前隊伍</span>
          <span class="text-xs opacity-80">僅分享目前編輯的隊伍 1 隊</span>
        </div>
      </el-button>
      <el-button type="warning" plain size="large" @click="$emit('share', { scope: 'inventory', asPublic: false })" class="w-full !m-0">
        <div class="flex flex-col items-center">
          <span class="font-bold">僅分享庫存</span>
          <span class="text-xs opacity-80">請教他人配將用</span>
        </div>
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import UserTag from '../UserTag.vue'

export type ShareScope = 'all' | 'current' | 'inventory'
export interface ShareEventPayload {
  scope: ShareScope
  asPublic: boolean
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  name: string
  isLoggedIn: boolean
  displayName: string | null
  userId?: string | null
  groupName: string
  isBanned?: boolean
}>(), {
  userId: null,
  isBanned: false,
})
defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:name', v: string): void
  (e: 'share', payload: ShareEventPayload): void
}>()

const asPublic = ref(false)

// Reset on every open so a leftover toggle doesn't surprise a future share.
watch(() => props.modelValue, (now) => {
  if (now) asPublic.value = false
})
</script>
