<template>
  <div class="h-full min-h-0 overflow-y-auto bg-slate-50 px-3 md:px-5 py-4">
    <div class="flex items-center gap-2 mb-3">
      <div class="text-xs text-ink-mute">
        {{ groupName }} · {{ filled.length }} 隊
      </div>
      <el-button
        size="small"
        plain
        class="!rounded-sm !ml-auto"
        :type="hideHeroArt ? 'primary' : 'default'"
        @click.stop="hideHeroArt = !hideHeroArt"
      >隱藏圖片</el-button>
    </div>
    <div v-if="filled.length === 0" class="text-center py-16 text-gray-400">
      尚未配置任何隊伍，先把武將放上陣。
    </div>
    <div v-else class="thumb-grid">
      <div
        v-for="item in filled"
        :key="item.idx"
        role="button"
        tabindex="0"
        class="compact-card"
        title="點擊即可回到編輯此隊伍"
        @click="$emit('select', item.idx)"
        @keydown.enter="$emit('select', item.idx)"
        @keydown.space.prevent="$emit('select', item.idx)"
      >
        <TeamPreviewCard :team="item.team" density="compact" :hide-hero-art="hideHeroArt" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import TeamPreviewCard from '../preview/TeamPreviewCard.vue'
import { isEmptyTeam, type Lineup } from '../../composables/useLineups'

const props = defineProps<{
  lineups: Lineup[]
  groupName: string
}>()

defineEmits<{
  (e: 'select', idx: number): void
}>()

const hideHeroArt = ref(false)

const filled = computed(() =>
  props.lineups
    .map((team, idx) => ({ team, idx }))
    .filter(({ team }) => !isEmptyTeam(team)),
)
</script>

<style scoped>
.thumb-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}
@media (min-width: 640px) {
  .thumb-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (min-width: 1024px) {
  .thumb-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
.compact-card {
  width: 100%;
  min-width: 0;
  cursor: pointer;
  border-radius: 12px;
}
/* Compact portraits are a fixed 104px square; shrink them with the
   4-col card so the hero row does not overflow. */
.compact-card :deep(.preview-portrait) {
  width: 100%;
  height: auto;
  aspect-ratio: 1;
  max-width: 104px;
}
.compact-card:hover,
.compact-card:focus-visible {
  outline: 2px solid rgb(var(--color-focus));
  outline-offset: 2px;
}
</style>
