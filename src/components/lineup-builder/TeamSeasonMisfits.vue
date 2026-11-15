<template>
  <span
    v-if="count > 0"
    class="season-count"
    :title="`這支隊伍有 ${count} 項 ${gameSeason} 沒有的武將或戰法`"
    data-testid="team-season-misfits"
  >{{ count }}</span>
</template>

<script setup lang="ts">
// A team row's count of what the picked game season does not offer (../../composables/useGameSeason.ts).
import { computed } from 'vue'
import { useGameSeason } from '../../composables/useGameSeason'

const props = defineProps<{ team: number }>()
const { gameSeason, misfitCounts } = useGameSeason()
const count = computed(() => misfitCounts.value[props.team] ?? 0)
</script>

<style scoped>
/* The same red count as the season pill's badge. */
.season-count {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: #dc2626;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
}
</style>
