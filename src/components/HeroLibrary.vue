<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- Filters -->
    <div class="p-2 border-b border-gray-100 space-y-2">
      <div class="flex justify-between items-center">
        <el-input 
          v-model="searchQuery" 
          placeholder="搜尋武將..." 
          clearable 
          prefix-icon="Search"
          class="flex-1 mr-2"
        />
        <el-switch 
          :model-value="filterOwned"
          @update:model-value="val => $emit('update:filterOwned', val)"
          inline-prompt 
          active-text="已擁有" 
          inactive-text="全部"
          v-if="mode === 'select'"
        />
         <div v-else class="text-xs font-bold text-gray-500 bg-gray-100 px-2 py-1 rounded">
           庫存編輯模式
         </div>
      </div>

      <div class="space-y-1 pb-1">
        <div class="flex items-center gap-1">
          <span class="text-xs text-gray-400 w-8 flex-shrink-0">Cost</span>
          <div class="flex gap-1 flex-wrap flex-1">
            <button
              v-for="c in availableCosts"
              :key="'cost-' + c"
              class="px-2 py-0.5 text-xs rounded border transition-colors"
              :class="selectedCosts.has(c)
                ? 'bg-blue-500 text-white border-blue-500'
                : 'bg-white text-gray-500 border-gray-300 hover:border-blue-300'"
              @click="toggleCost(c)"
            >{{ c }}</button>
          </div>
          <button
            v-if="hasActiveFilters"
            class="text-xs font-bold text-red-500 hover:text-red-700 transition-colors flex-shrink-0"
            @click="resetFilters"
          >✕</button>
        </div>
        <div class="flex items-center gap-1">
          <span class="text-xs text-gray-400 w-8 flex-shrink-0">勢力</span>
          <div class="flex gap-1 flex-wrap">
            <button
              v-for="f in factions"
              :key="'fac-' + f"
              class="px-2 py-0.5 text-xs rounded border transition-colors"
              :class="selectedFactions.has(f)
                ? 'bg-amber-500 text-white border-amber-500'
                : 'bg-white text-gray-500 border-gray-300 hover:border-amber-300'"
              @click="toggleFaction(f)"
            >{{ f }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Grid -->
    <div class="flex-1 overflow-y-auto p-2" v-loading="loading">
      <div v-if="filteredHeroes.length === 0" class="text-center py-10 text-gray-400">
        無符合條件的武將
      </div>
      <div 
        class="grid gap-2"
        :class="mode === 'manage' ? 'grid-cols-5 sm:grid-cols-8 md:grid-cols-10' : 'grid-cols-3 sm:grid-cols-4'"
      >
        <div 
          v-for="hero in filteredHeroes" 
          :key="hero.name + hero.faction" 
          class="relative transition-all"
          :class="{ 
            'opacity-50 grayscale cursor-not-allowed': mode === 'select' && isUsed(hero.name),
            'opacity-40': mode === 'select' && filterOwned && !props.ownedHeroes.includes(hero.name),
            'grayscale opacity-60': mode === 'manage' && !props.ownedHeroes.includes(hero.name),
            'cursor-pointer hover:scale-105': (mode === 'manage') || (mode === 'select' && !isUsed(hero.name))
          }"
          @click="handleClick(hero)"
        >
          <HeroCard :hero="hero" :show-aptitude="mode !== 'manage'" :compact="mode === 'manage'" />
          
          <!-- Used Label (Select Mode) -->
          <div v-if="mode === 'select' && isUsed(hero.name)" class="absolute inset-0 flex items-center justify-center z-20">
             <span class="bg-black/70 text-white text-xs px-2 py-1 rounded font-bold">已上陣</span>
          </div>

          <!-- Unowned Label (Manage Mode) -->
           <div v-if="mode === 'manage' && !props.ownedHeroes.includes(hero.name)" class="absolute inset-0 flex items-center justify-center z-20 pointer-events-none">
             <!-- Icon only for compact mode? Or just dimming is enough? -->
             <!-- <span class="bg-gray-800/70 text-white text-xs px-1 py-0.5 rounded">未擁有</span> -->
             <el-icon class="text-white bg-black/50 rounded-full p-1" :size="20"><Close /></el-icon>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, PropType, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { useData, Hero } from '../composables/useData'
import HeroCard from './HeroCard.vue'

const { heroes, loading } = useData()
const emit = defineEmits(['select', 'update:ownedHeroes', 'update:filterOwned'])

const props = defineProps({
  usedHeroes: { type: Object as PropType<Set<string> | string[]>, default: () => [] },
  mode: { type: String as PropType<'select' | 'manage'>, default: 'select' },
  ownedHeroes: { type: Array as PropType<string[]>, default: () => [] },
  filterOwned: { type: Boolean, default: false }
})

const searchQuery = ref('')
const debouncedSearchQuery = ref('')
let debounceTimer: any = null

watch(searchQuery, (newVal) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debouncedSearchQuery.value = newVal
  }, 200)
})

const selectedCosts = ref<Set<number>>(new Set())
const selectedFactions = ref<Set<string>>(new Set())

const factions = computed(() => {
  return [...new Set(heroes.value.map(h => h.faction))].filter(Boolean).sort()
})

const availableCosts = computed(() => {
  return [...new Set(heroes.value.map(h => h.cost))].sort((a, b) => b - a)
})

const toggleCost = (cost: number) => {
  const next = new Set(selectedCosts.value)
  next.has(cost) ? next.delete(cost) : next.add(cost)
  selectedCosts.value = next
}

const toggleFaction = (faction: string) => {
  const next = new Set(selectedFactions.value)
  next.has(faction) ? next.delete(faction) : next.add(faction)
  selectedFactions.value = next
}

const hasActiveFilters = computed(() => selectedCosts.value.size > 0 || selectedFactions.value.size > 0)

const resetFilters = () => {
  selectedCosts.value = new Set()
  selectedFactions.value = new Set()
}

const filteredHeroes = computed(() => {
  return heroes.value.filter(h => {
    if (debouncedSearchQuery.value && !h.name.includes(debouncedSearchQuery.value)) return false
    if (selectedFactions.value.size > 0 && !selectedFactions.value.has(h.faction)) return false
    if (selectedCosts.value.size > 0 && !selectedCosts.value.has(h.cost)) return false
    if (props.mode === 'select' && props.filterOwned && !props.ownedHeroes.includes(h.name)) return false
    return true
  })
})

const isUsed = (name: string) => {
  if (Array.isArray(props.usedHeroes)) {
    return props.usedHeroes.includes(name)
  }
  return (props.usedHeroes as Set<string>).has(name)
}

const toggleOwned = (name: string) => {
  const newOwned = [...props.ownedHeroes]
  if (newOwned.includes(name)) {
    newOwned.splice(newOwned.indexOf(name), 1)
  } else {
    newOwned.push(name)
  }
  emit('update:ownedHeroes', newOwned)
}

const handleClick = (hero: Hero) => {
  if (props.mode === 'manage') {
    toggleOwned(hero.name)
  } else {
    // Select mode
    // Check if used
    if (isUsed(hero.name)) return
    // Check if owned (if we enforce ownership, strictly speaking yes, but usually just visual warning)
    // Let's assume user can only select what they own if filter is on, otherwise allow ghosting? 
    // Usually "Inventory" implies you can only use what you have. 
    // But for a builder, maybe allow all? Let's assume allow all unless filtered.
    emit('select', hero)
  }
}
</script>
