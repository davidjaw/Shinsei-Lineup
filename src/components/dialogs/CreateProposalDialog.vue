<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    title="另存為精選隊伍"
    width="380px"
    align-center
  >
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-ink-mute">隊伍名稱</label>
        <el-input
          v-model="name"
          maxlength="50"
          placeholder="例如：突騎奇襲一波流"
          show-word-limit
          clearable
        />
      </div>

      <div
        v-if="isLoggedIn"
        class="flex items-center justify-between pt-1 border-t border-divider"
      >
        <div class="flex flex-col gap-0.5">
          <span class="text-sm">公開分享</span>
          <span class="text-[11px] text-ink-mute leading-snug">
            {{ isBanned ? '此帳號已被封鎖，無法公開分享' : '開啟後將出現在「精選隊伍」公開列表' }}
          </span>
        </div>
        <el-switch v-model="isPublic" :disabled="isBanned" />
      </div>
      <p v-else class="text-[11px] text-ink-mute leading-snug">
        未登入只能存為本機草稿；登入後可選公開分享。
      </p>

      <div class="flex justify-end gap-2 pt-1">
        <el-button @click="onCancel">取消</el-button>
        <el-button type="primary" :disabled="!nameValid" :loading="submitting" @click="onSubmit">
          儲存
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  isLoggedIn: boolean
  submitting: boolean
  isBanned?: boolean
}>(), {
  isBanned: false,
})
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submit', payload: { name: string; isPublic: boolean }): void
}>()

const name = ref('')
const isPublic = ref(false)

const nameValid = computed(() => name.value.trim().length > 0)

// Reset on open so a previous submission doesn't leak back into a new one.
watch(() => props.modelValue, (now) => {
  if (now) {
    name.value = ''
    isPublic.value = false
  }
})

const onCancel = () => emit('update:modelValue', false)

const onSubmit = () => {
  if (!nameValid.value) return
  emit('submit', {
    name: name.value.trim(),
    isPublic: props.isLoggedIn && !props.isBanned ? isPublic.value : false,
  })
}
</script>
