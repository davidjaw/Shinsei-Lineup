<template>
  <span
    v-if="mark"
    class="skill-type-mark font-brand"
    :class="[
      `skill-type-mark--${size}`,
      `skill-type-mark--${tone}`,
      { 'skill-type-mark--own': own, 'skill-type-mark--muted': muted },
    ]"
    :title="label"
  >{{ mark }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { skillTypeMark, skillTypeTone } from '../constants/gameData'

const props = withDefaults(defineProps<{
  type?: string | null
  size?: 'slot' | 'list' | 'drag'
  /** Filled seal — unique/own skill, same character, stronger stamp. */
  own?: boolean
  muted?: boolean
}>(), {
  size: 'slot',
  own: false,
  muted: false,
})

const mark = computed(() => skillTypeMark(props.type))
const tone = computed(() => skillTypeTone(props.type))
const label = computed(() => props.type || '')
</script>

<style scoped>
.skill-type-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 700;
  line-height: 1;
  user-select: none;
  border: 1px solid transparent;
}
.skill-type-mark--slot {
  width: 1.25rem;
  height: 1.25rem;
  font-size: 9px;
  border-radius: 4px;
}
.skill-type-mark--list {
  width: 1.75rem;
  height: 1.75rem;
  font-size: 11px;
  border-radius: 6px;
}
.skill-type-mark--drag {
  width: 2.5rem;
  height: 2.5rem;
  font-size: 15px;
  border-radius: 8px;
}
@media (min-width: 768px) {
  .skill-type-mark--slot {
    width: 2rem;
    height: 2rem;
    font-size: 13px;
  }
  .skill-type-mark--list {
    width: 2.5rem;
    height: 2.5rem;
    font-size: 15px;
    border-radius: 8px;
  }
}
.skill-type-mark--slot.skill-type-mark--own {
  font-size: calc(9px * 1.3);
}
@media (min-width: 768px) {
  .skill-type-mark--slot.skill-type-mark--own {
    font-size: calc(13px * 1.3);
  }
}
/* Gold seal — 主動 / 突擊 / 指揮 */
.skill-type-mark--action {
  background: rgb(var(--color-highlight));
  color: rgb(var(--color-focus));
  border-color: rgb(var(--color-brand) / 0.55);
}
/* Muted ink — 被動 */
.skill-type-mark--passive {
  background: rgb(var(--color-surface-muted));
  color: #475569;
  border-color: rgb(var(--color-divider));
}
/* Brown stamp matching preview meta/own-tag — 兵種 / 陣法 */
.skill-type-mark--meta {
  background: rgba(180, 83, 9, 0.1);
  color: #b45309;
  border-color: rgba(180, 83, 9, 0.35);
}
.skill-type-mark--unknown {
  background: rgb(var(--color-surface-muted));
  color: #94a3b8;
  border-color: rgb(var(--color-divider));
}
/* Unique/own: filled ink-seal vs the outlined paper stamp above. */
.skill-type-mark--own.skill-type-mark--action {
  background: linear-gradient(160deg, #d4a84a 0%, #b89127 52%, #8f6f14 100%);
  color: #fffdf5;
  border-color: #8f6f14;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35);
}
.skill-type-mark--own.skill-type-mark--passive {
  background: linear-gradient(160deg, #7b8796 0%, #5b6775 100%);
  color: #f8fafc;
  border-color: #475569;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
}
.skill-type-mark--own.skill-type-mark--meta {
  background: linear-gradient(160deg, #d97706 0%, #b45309 100%);
  color: #fffdf5;
  border-color: #92400e;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
}
.skill-type-mark--own.skill-type-mark--unknown {
  background: linear-gradient(160deg, #cbd5e1 0%, #94a3b8 100%);
  color: #fff;
  border-color: #64748b;
}
.skill-type-mark--muted {
  opacity: 0.45;
  filter: grayscale(1);
}
</style>
