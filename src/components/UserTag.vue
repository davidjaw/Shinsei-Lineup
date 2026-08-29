<template>
  <span class="user-tag">
    <SpoilerText v-if="hidden || locked" :locked="locked" class="tag-body">{{ shownName }}</SpoilerText>
    <span v-else class="tag-body">{{ shownName }}</span>
    <span v-if="hex" class="tag-hex">#{{ hex }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { userHex } from '../lib/displayName'
import SpoilerText from './SpoilerText.vue'

const props = withDefaults(defineProps<{
  name: string
  userId?: string | null
  hidden?: boolean
  locked?: boolean
}>(), {
  userId: null,
  hidden: false,
  locked: false,
})

const shownName = computed(() => props.name.trim() || '匿名')
const hex = computed(() => userHex(props.userId))
</script>

<style scoped>
.user-tag {
  display: inline-flex;
  align-items: baseline;
  min-width: 0;
  max-width: 100%;
  gap: 1px;
}
.tag-body {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.tag-hex {
  flex-shrink: 0;
  font-size: 0.78em;
  font-weight: 500;
  letter-spacing: 0.03em;
  color: #64748b;
}
.user-tag :deep(.spoiler) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
</style>
