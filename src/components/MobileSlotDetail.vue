<template>
  <div class="flex flex-col h-full bg-slate-50 p-4 overflow-y-auto">
    
    <!-- Header with Radar -->
    <div class="flex items-center gap-4 mb-6">
      <div class="flex-shrink-0 bg-white rounded-full p-2 shadow-sm border border-gray-100" @click="$emit('open-stats')">
        <RadarChart :stats="stats" :base-stats="hero?.stats" :size="100" />
        <div class="text-[10px] text-center text-indigo-500 mt-1"><el-icon><Edit /></el-icon> 配點</div>
      </div>
      
      <div class="flex-1 space-y-2">
         <div class="font-bold text-lg text-gray-800">{{ roleName }} - {{ hero?.name }}</div>
         <div class="text-xs text-gray-500">
            <div class="flex justify-between border-b border-gray-200 py-1"><span>統帥</span> <span class="font-bold text-gray-800">{{ stats.lea }}</span></div>
            <div class="flex justify-between border-b border-gray-200 py-1"><span>武勇</span> <span class="font-bold text-gray-800">{{ stats.val }}</span></div>
            <div class="flex justify-between border-b border-gray-200 py-1"><span>智略</span> <span class="font-bold text-gray-800">{{ stats.int }}</span></div>
         </div>
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

    <!-- Equip Traits Section -->
    <div class="bg-white rounded-lg p-3 shadow-sm border border-gray-100 mb-4">
      <div class="text-sm font-bold text-gray-700 mb-2 border-l-4 border-amber-500 pl-2">裝備特性</div>
      <div class="grid grid-cols-2 gap-2">
         <div 
            v-for="(trait, idx) in equipTraits || [null, null, null, null]" 
            :key="'eq'+idx" 
            class="flex flex-col items-center justify-center p-2 rounded border border-dashed h-16 cursor-pointer hover:bg-gray-50"
            :class="trait ? getTraitColor(trait.rank) + ' border-solid' : 'border-gray-300 text-gray-400'"
            @click="$emit('open-equip', idx)"
          >
            <span v-if="trait" class="font-bold text-sm">{{ trait.name }}</span>
            <el-icon v-else class="text-xl"><Plus /></el-icon>
            <span v-if="trait" class="text-[10px] mt-1 opacity-80 truncate w-full text-center">{{ resolveTraitDesc(trait) }}</span>
          </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { PropType, ref, watch } from 'vue'
import { Edit, Plus } from '@element-plus/icons-vue'
import RadarChart from './RadarChart.vue'
import { Hero, Trait } from '../composables/useData'
import { useTemplateParser } from '../composables/useTemplateParser'

const { parseTextToPlain } = useTemplateParser()
const resolveTraitDesc = (trait: any) => {
  if (!trait?.description) return '無描述'
  return parseTextToPlain(trait.description, false, (trait as any).vars)
}

const props = defineProps({
  roleName: String,
  hero: Object as PropType<Hero | null>,
  stats: { type: Object as PropType<any>, required: true },
  equipTraits: Array as PropType<Trait[]>
})

const emit = defineEmits(['update:hero', 'open-stats', 'open-equip']) // traits update logic is internal to hero object for now, or we can emit update

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

const getTraitColor = (rank: string) => {
  switch (rank) {
    case 'S': return 'bg-yellow-50 border-yellow-200 text-yellow-800'
    case 'A': return 'bg-purple-50 border-purple-200 text-purple-800'
    case 'B': return 'bg-blue-50 border-blue-200 text-blue-800'
    default: return 'bg-gray-50 border-gray-200 text-gray-500'
  }
}
</script>