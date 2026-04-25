<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- Filters -->
    <div class="p-0 md:p-2 border-b border-gray-100 space-y-1 md:space-y-2">
      <div class="flex justify-between items-center px-1 md:px-0 pt-1 md:pt-0">
        <el-input
          v-model="searchQuery"
          placeholder="搜尋武將..."
          clearable
          prefix-icon="Search"
          class="flex-1 mr-1 md:mr-2"
          size="small"
        />
        <button
          class="relative px-2 py-1 text-xs rounded border mr-2 transition-colors flex-shrink-0"
          :class="showFilters
            ? 'bg-gray-700 text-white border-gray-700'
            : 'bg-white text-gray-500 border-gray-300 hover:border-gray-500'"
          @click="showFilters = !showFilters"
          :title="showFilters ? '隱藏篩選' : '顯示篩選'"
        >
          篩選
          <span
            v-if="activeFilterCount > 0"
            class="absolute -top-1 -right-1 bg-red-500 text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px] font-bold"
          >{{ activeFilterCount }}</span>
        </button>
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

      <div v-show="showFilters" class="space-y-1 pb-1 px-1 md:px-0">
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
        <div class="flex items-start gap-1">
          <span class="text-xs text-gray-400 w-8 flex-shrink-0 mt-0.5">家門</span>
          <div class="flex gap-1 flex-wrap">
            <button
              v-for="c in clans"
              :key="'clan-' + c"
              class="px-2 py-0.5 text-xs rounded border transition-colors"
              :class="selectedClans.has(c)
                ? 'bg-emerald-500 text-white border-emerald-500'
                : 'bg-white text-gray-500 border-gray-300 hover:border-emerald-300'"
              @click="toggleClan(c)"
            >{{ c }}</button>
          </div>
        </div>
        <div class="flex items-center gap-1">
          <span class="text-xs text-gray-400 w-8 flex-shrink-0">兵種</span>
          <div class="flex gap-1 flex-wrap">
            <button
              v-for="tt in TROOP_TYPES"
              :key="'troop-' + tt"
              class="px-2 py-0.5 text-xs rounded border transition-colors"
              :class="selectedTroopTypes.has(tt)
                ? 'bg-red-500 text-white border-red-500'
                : 'bg-white text-gray-500 border-gray-300 hover:border-red-300'"
              @click="toggleTroopType(tt)"
            >{{ tt }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Grid -->
    <div class="flex-1 overflow-y-auto p-0 md:p-2" v-loading="loading">
      <div v-if="filteredHeroes.length === 0" class="text-center py-10 text-gray-400">
        無符合條件的武將
      </div>
      <div
        class="grid gap-1 md:gap-2"
        :class="mode === 'manage' ? 'grid-cols-5 sm:grid-cols-8 md:grid-cols-10' : 'grid-cols-4 sm:grid-cols-4'"
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
import { TROOP_TYPES } from '../constants/traits'
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

const showFilters = ref(false)
const selectedCosts = ref<Set<number>>(new Set())
const selectedFactions = ref<Set<string>>(new Set())
const selectedClans = ref<Set<string>>(new Set())
const selectedTroopTypes = ref<Set<string>>(new Set())

const factions = computed(() => {
  return [...new Set(heroes.value.map(h => h.faction))].filter(Boolean).sort()
})

const clans = computed(() => {
  const counts = new Map<string, number>()
  for (const h of heroes.value) {
    if (!h.clan) continue
    counts.set(h.clan, (counts.get(h.clan) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c)
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

const toggleClan = (clan: string) => {
  const next = new Set(selectedClans.value)
  next.has(clan) ? next.delete(clan) : next.add(clan)
  selectedClans.value = next
}

const toggleTroopType = (tt: string) => {
  const next = new Set(selectedTroopTypes.value)
  next.has(tt) ? next.delete(tt) : next.add(tt)
  selectedTroopTypes.value = next
}

const heroHasTroopType = (h: Hero, types: Set<string>): boolean => {
  return (h.traits || []).some(t =>
    t.affinity?.troop_types?.some(tt => types.has(tt))
  )
}

const activeFilterCount = computed(() => selectedCosts.value.size + selectedFactions.value.size + selectedClans.value.size + selectedTroopTypes.value.size)
const hasActiveFilters = computed(() => activeFilterCount.value > 0)

const resetFilters = () => {
  selectedCosts.value = new Set()
  selectedFactions.value = new Set()
  selectedClans.value = new Set()
  selectedTroopTypes.value = new Set()
}

const filteredHeroes = computed(() => {
  return heroes.value.filter(h => {
    if (debouncedSearchQuery.value && !h.name.includes(debouncedSearchQuery.value)) return false
    if (selectedFactions.value.size > 0 && !selectedFactions.value.has(h.faction)) return false
    if (selectedCosts.value.size > 0 && !selectedCosts.value.has(h.cost)) return false
    if (selectedClans.value.size > 0 && (!h.clan || !selectedClans.value.has(h.clan))) return false
    if (selectedTroopTypes.value.size > 0 && !heroHasTroopType(h, selectedTroopTypes.value)) return false
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
