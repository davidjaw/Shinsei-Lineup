<template>
  <div class="flex flex-col gap-2 h-full">
    <!-- Header: search + counter -->
    <div class="flex items-center gap-2 flex-shrink-0">
      <el-input
        v-model="searchQuery"
        placeholder="搜尋武將"
        size="small"
        clearable
        class="!w-32 md:!w-48"
      />
      <span class="text-[11px] text-gray-400">
        S 級 {{ ssrHeroes.length }} · 已選 {{ selectedSet.size }}
      </span>
      <div class="ml-auto flex gap-1">
        <el-button size="small" plain @click="selectAll">全選 S</el-button>
        <el-button size="small" plain @click="clearAll">清空</el-button>
      </div>
    </div>

    <!-- S-tier hero grid -->
    <div class="flex-1 overflow-y-auto px-0.5">
      <div v-if="filteredHeroes.length === 0" class="text-center text-gray-400 py-10 text-sm">
        無符合條件的武將
      </div>
      <div
        v-else
        class="grid grid-cols-5 gap-1 lg:grid-cols-10"
      >
        <button
          v-for="hero in filteredHeroes"
          :key="hero.name_jp || hero.name"
          class="relative aspect-[3/4] rounded-md overflow-hidden border-2 transition-all bg-white cursor-pointer focus:outline-none"
          :class="isSelected(hero)
            ? 'border-orange-500 shadow shadow-orange-200'
            : 'border-gray-200 opacity-60 hover:opacity-100 hover:border-gray-400'"
          @click="onToggle(hero)"
        >
          <img
            :src="hero.portrait"
            class="w-full h-full object-cover object-top pointer-events-none"
            loading="lazy"
            @error="handleImageError"
          />
          <!-- name overlay -->
          <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-0.5 pt-1.5 pb-0.5 pointer-events-none">
            <div class="text-white text-[9px] truncate text-center font-bold">{{ hero.name }}</div>
          </div>
          <!-- selected checkmark -->
          <div
            v-if="isSelected(hero)"
            class="absolute top-0 right-0 w-5 h-5 flex items-center justify-center bg-orange-500 text-white pointer-events-none"
          >
            <el-icon class="text-xs"><Check /></el-icon>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, PropType, ref, watch } from 'vue'
import { ElButton, ElIcon, ElInput } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import type { Hero } from '../composables/useData'

const props = defineProps({
  heroes: { type: Array as PropType<Hero[]>, required: true },
  /** Currently selected heroes by CHT name. Mirrors HeroLibrary's contract
   *  so the parent's CHT↔JP conversion logic stays the same. */
  modelValue: { type: Array as PropType<string[]>, required: true },
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: string[]): void
}>()

const searchQuery = ref('')
const debouncedSearch = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, (v) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debouncedSearch.value = v }, 200)
})
onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
})

// rarity == 5 → S tier. Strings/numbers both compared via Number() coercion
// because the source JSON has mixed types historically.
const ssrHeroes = computed<Hero[]>(() =>
  props.heroes.filter(h => Number(h.rarity) === 5),
)

const filteredHeroes = computed<Hero[]>(() => {
  const q = debouncedSearch.value.trim()
  if (!q) return ssrHeroes.value
  return ssrHeroes.value.filter(h =>
    h.name.includes(q) || (h.name_jp || '').includes(q),
  )
})

const selectedSet = computed<Set<string>>(() => new Set(props.modelValue))

const isSelected = (h: Hero): boolean => selectedSet.value.has(h.name)

const onToggle = (h: Hero): void => {
  const next = new Set(props.modelValue)
  if (next.has(h.name)) next.delete(h.name)
  else next.add(h.name)
  emit('update:modelValue', Array.from(next))
}

const selectAll = (): void => {
  emit('update:modelValue', ssrHeroes.value.map(h => h.name))
}

const clearAll = (): void => {
  emit('update:modelValue', [])
}

const IMG_PLACEHOLDER =
  "data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 90 120'><rect width='90' height='120' fill='%23e5e7eb'/><text x='45' y='65' text-anchor='middle' font-family='sans-serif' font-size='10' fill='%239ca3af'>No%20Img</text></svg>"

const handleImageError = (e: Event) => {
  (e.target as HTMLImageElement).src = IMG_PLACEHOLDER
}
</script>
