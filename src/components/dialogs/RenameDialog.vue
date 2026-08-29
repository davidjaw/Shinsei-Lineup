<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    title="設定顯示名稱"
    width="340px"
    align-center
  >
    <div class="flex flex-col gap-3 pb-1">
      <p class="text-xs text-gray-500 -mt-1 mb-1">
        此名稱會顯示在公開精選的作者欄。後方的識別碼由系統產生，無法修改。
      </p>
      <el-input
        :model-value="name"
        @update:model-value="(v: string) => $emit('update:name', v)"
        maxlength="30"
        show-word-limit
        placeholder="例：張三"
        @keyup.enter="$emit('submit')"
        autofocus
      />
      <p v-if="name.trim()" class="text-[11px] text-ink-mute leading-snug -mt-1">
        公開顯示為：<UserTag class="align-baseline" :name="name.trim()" :user-id="userId" />
      </p>
      <el-button
        type="primary"
        :loading="saving"
        @click="$emit('submit')"
        class="w-full !m-0"
      >
        確定
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import UserTag from '../UserTag.vue'

defineProps<{
  modelValue: boolean
  name: string
  saving: boolean
  userId?: string | null
}>()
defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:name', v: string): void
  (e: 'submit'): void
}>()
</script>
