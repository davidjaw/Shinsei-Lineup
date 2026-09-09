<template>
  <div class="flex flex-col h-full bg-slate-50 p-4 overflow-y-auto">
    
    <!-- Header + stats table (tap opens free-point editor) -->
    <div class="mb-4">
      <div class="font-bold text-lg text-gray-800 mb-3">{{ roleName }} - {{ hero?.name }}</div>
      <div
        class="bg-white rounded-lg p-3 shadow-sm border border-gray-100 cursor-pointer active:bg-slate-50"
        :title="`點擊調整自由加點 · 剩餘 ${freePointsRemaining} 點`"
        @click="openStatsEditor"
      >
        <div class="grid grid-cols-3 gap-2">
          <div
            v-for="key in STAT_KEYS"
            :key="key"
            class="flex flex-col items-center py-1"
          >
            <span class="text-[11px] text-gray-500 mb-0.5">{{ STAT_LABELS[key] }}</span>
            <span class="text-base font-bold text-gray-800 leading-none">{{ stats[key] }}</span>
            <span v-if="bonus(key) > 0" class="text-[10px] text-emerald-600 mt-0.5">+{{ bonus(key) }}</span>
            <span v-else-if="bonus(key) < 0" class="text-[10px] text-red-500 mt-0.5">{{ bonus(key) }}</span>
            <span v-else class="text-[10px] text-transparent mt-0.5 select-none">·</span>
          </div>
        </div>
        <div class="text-[10px] text-gray-400 text-center mt-2">點擊調整自由加點 · 剩餘 {{ freePointsRemaining }} 點</div>
      </div>
    </div>

    <!-- Traits Section -->
    <div class="bg-white rounded-lg p-3 shadow-sm border border-gray-100 mb-4">
      <div class="text-sm font-bold text-gray-700 mb-2 border-l-4 border-indigo-500 pl-2">固有/自選特性</div>
      <div class="grid grid-cols-2 gap-2">
        <div 
          v-for="(trait, idx) in localTraits" 
          :key="idx"
          class="flex flex-col p-2 rounded border transition-colors cursor-pointer"
          :class="[
            getTraitColor(trait.rank),
            { 'opacity-50 grayscale': !trait.active, 'ring-2 ring-indigo-200': trait.active }
          ]"
          @click="toggleTrait(idx)"
        >
          <span class="font-bold text-sm text-center">{{ trait.name }}</span>
          <span class="text-[10px] text-center mt-1 opacity-80 truncate">{{ resolveTraitDesc(trait) }}</span>
        </div>
      </div>
    </div>

    <StatsEditorDialog
      v-model="statsDialogVisible"
      :hero="hero"
      :stats="stats"
      :breakthrough="breakthrough"
      @update:stats="(s) => emit('update:stats', s)"
    />
  </div>
</template>

<script setup lang="ts">
import { PropType, computed, ref, watch } from 'vue'
import { Hero, Trait } from '../composables/useData'
import { getTraitColor } from '../constants/gameData'
import { useTemplateParser } from '../composables/useTemplateParser'
import type { RoleData } from '../composables/useLineups'
import StatsEditorDialog from './StatsEditorDialog.vue'

const { parseTextToPlain } = useTemplateParser()
const resolveTraitDesc = (trait: any) => {
  if (!trait?.description) return '說明: 尚未建立資料'
  return parseTextToPlain(trait.description, false, (trait as any).vars)
}

const props = defineProps({
  roleName: String,
  hero: Object as PropType<Hero | null>,
  stats: { type: Object as PropType<any>, required: true },
  breakthrough: { type: Number, default: 0 },
})

const emit = defineEmits<{
  (e: 'update:stats', stats: RoleData['stats']): void
}>()

const STAT_KEYS = ['lea', 'val', 'int', 'pol', 'cha', 'spd'] as const
const STAT_LABELS: Record<typeof STAT_KEYS[number], string> = {
  lea: '統', val: '武', int: '智', pol: '政', cha: '魅', spd: '速',
}
const bonus = (key: typeof STAT_KEYS[number]): number =>
  (props.stats?.[key] ?? 0) - (props.hero?.stats?.[key] ?? 0)

const freePointsTotal = computed(() => 50 + (props.breakthrough ?? 0) * 10)
const freePointsRemaining = computed(() => {
  let used = 0
  for (const k of STAT_KEYS) used += Math.max(0, bonus(k))
  return freePointsTotal.value - used
})

const statsDialogVisible = ref(false)
const openStatsEditor = () => {
  if (!props.hero) return
  statsDialogVisible.value = true
}


// Trait Logic (Similar to LineupSlot but simplified for display/toggle)
const localTraits = ref<Trait[]>([])

const initializeTraits = () => {
  if (!props.hero) {
    localTraits.value = []
    return
  }
  const existing = props.hero.traits || []
  const defaults: Trait[] = [
    { name: '固有', rank: 'S', active: true },
    { name: '特性 2', rank: 'A', active: false },
    { name: '特性 3', rank: 'B', active: false },
    { name: '特性 4', rank: 'C', active: false }
  ]
  localTraits.value = defaults.map((def, i) => existing[i] ? { ...existing[i], active: existing[i].active ?? true } : def)
}

watch(() => props.hero, initializeTraits, { immediate: true })

const toggleTrait = (index: number) => {
  if (index === 0) return 
  const trait = localTraits.value[index]
  if (trait) {
    trait.active = !trait.active
  }
}

</script>