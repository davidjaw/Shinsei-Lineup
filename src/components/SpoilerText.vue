<template>
  <span
    v-if="locked"
    class="spoiler spoiler--locked"
    title="已永久隱藏"
    aria-label="已永久隱藏"
  >
    <span class="spoiler-inner">••••</span>
  </span>
  <button
    v-else
    type="button"
    class="spoiler"
    :class="{ revealed }"
    :title="revealed ? '點擊隱藏名稱' : '點擊顯示名稱'"
    :aria-label="revealed ? '點擊隱藏名稱' : '點擊顯示名稱'"
    @click.stop="revealed = !revealed"
  >
    <span class="spoiler-inner"><slot /></span>
  </button>
</template>

<script setup lang="ts">
import { ref } from 'vue'

withDefaults(defineProps<{
  locked?: boolean
}>(), {
  locked: false,
})

const revealed = ref(false)
</script>

<style scoped>
/* Discord-style spoiler: text is present but painted the same as the bar
   until the reader opts in. Click toggles. Locked: bar only, no slot text. */
.spoiler {
  display: inline;
  margin: 0;
  padding: 0 4px;
  border: 0;
  border-radius: 3px;
  background: #1f2937;
  color: transparent;
  font: inherit;
  font-weight: inherit;
  line-height: 1.35;
  cursor: pointer;
  user-select: none;
  vertical-align: baseline;
  max-width: 100%;
}
.spoiler:hover:not(.revealed):not(.spoiler--locked) {
  background: #374151;
}
.spoiler.revealed {
  background: rgba(31, 41, 55, 0.12);
  color: inherit;
  user-select: text;
}
.spoiler--locked {
  cursor: default;
  color: transparent;
}
.spoiler-inner {
  color: inherit;
}
</style>
