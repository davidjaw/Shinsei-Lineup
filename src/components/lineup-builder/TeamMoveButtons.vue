<template>
  <span class="inline-flex flex-shrink-0">
    <button
      type="button"
      class="move-btn"
      :class="size"
      data-move="earlier"
      :disabled="idx === 0"
      :aria-label="`${name} 上移（Alt + ↑）`"
      :title="`${name} 上移（Alt + ↑）`"
      @click.stop="$emit('step', $event, -1)"
      @keydown.enter.stop
      @keydown.space.stop
    >
      <el-icon :size="iconSize"><ArrowUp /></el-icon>
    </button>
    <button
      type="button"
      class="move-btn"
      :class="size"
      data-move="later"
      :disabled="idx === count - 1"
      :aria-label="`${name} 下移（Alt + ↓）`"
      :title="`${name} 下移（Alt + ↓）`"
      @click.stop="$emit('step', $event, 1)"
      @keydown.enter.stop
      @keydown.space.stop
    >
      <el-icon :size="iconSize"><ArrowDown /></el-icon>
    </button>
  </span>
</template>

<script setup lang="ts">
// Move this team one place: the path for touch and keyboard, where a native drag does not exist.
import { ArrowUp, ArrowDown } from '@element-plus/icons-vue'

defineProps<{ idx: number; count: number; name: string; size: 'w-5 h-6' | 'w-8 h-8'; iconSize: number }>()
defineEmits<{ (e: 'step', event: Event, step: -1 | 1): void }>()
</script>

<style scoped>
.move-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: #64748b;
  cursor: pointer;
}
.move-btn:hover:not(:disabled) {
  color: #1f2937;
  background: rgba(31, 41, 55, 0.06);
}
.move-btn:disabled {
  opacity: 0.3;
  cursor: default;
}
</style>
