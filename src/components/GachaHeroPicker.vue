<template>
  <div class="flex flex-col gap-2 h-full">
    <!-- Empty pool CTA -->
    <div
      v-if="poolHeroes.length === 0"
      class="flex flex-col items-center justify-center py-12 px-4 text-center bg-gray-50 rounded-lg"
    >
      <div class="text-sm text-gray-500 mb-3">尚未設定池內武將</div>
      <el-button type="primary" :icon="Edit" @click="emit('edit-pool')">
        編輯池內武將
      </el-button>
      <div class="text-[11px] text-gray-400 mt-2">
        定義這個池會出哪些武將後，才能開始登錄抽卡
      </div>
    </div>

    <template v-else>
      <!-- Search bar -->
      <div class="flex items-center gap-2 flex-shrink-0">
        <el-input
          v-model="searchQuery"
          placeholder="搜尋武將"
          size="small"
          clearable
          class="!w-32 md:!w-48"
        />
        <span class="text-[11px] text-gray-400">
          池內 {{ poolHeroes.length }} · 顯示 {{ filteredHeroes.length }}
        </span>
      </div>

      <!-- Hero grid: 6 cols mobile, 15 cols desktop -->
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
            class="relative aspect-[3/4] rounded-md overflow-hidden border bg-white cursor-pointer focus:outline-none focus:ring-2"
            :class="isHeroRare(hero)
              ? 'border-yellow-400 ring-2 ring-yellow-300/70 shadow shadow-yellow-300/60 focus:ring-yellow-400'
              : 'border-gray-200 hover:border-orange-400 hover:shadow-md focus:ring-orange-400'"
            @click="onPick(hero)"
          >
            <img
              :src="hero.portrait"
              class="w-full h-full object-cover object-top pointer-events-none"
              loading="lazy"
              @error="handleImageError"
            />
            <!-- Rare tint matches DrawCard so the picker reads the same way as
                 the history strip just above it. -->
            <div
              v-if="isHeroRare(hero)"
              class="absolute inset-0 bg-gradient-to-b from-yellow-300/30 via-transparent to-yellow-400/25 pointer-events-none"
            ></div>
            <div
              v-if="isHeroRare(hero)"
              class="absolute top-0 right-0 px-1 py-0.5 bg-yellow-400 text-white text-xs font-bold leading-none rounded-bl shadow pointer-events-none"
            >★</div>
            <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-0.5 pt-1.5 pb-0.5 pointer-events-none">
              <div class="text-white text-[9px] truncate text-center font-bold">{{ hero.name }}</div>
            </div>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, PropType, ref, watch } from 'vue'
import { ElButton, ElInput } from 'element-plus'
import { Edit } from '@element-plus/icons-vue'
import type { Hero } from '../composables/useData'

const props = defineProps({
  heroes: { type: Array as PropType<Hero[]>, required: true },
  /** JP names of heroes that belong to this banner. Empty = pool not defined. */
  pool: { type: Array as PropType<string[]>, required: true },
  /** JP-name → marked-draw count for the current banner. Heroes with count > 0
   *  are flagged "rare" (one of the user's marked picks). Optional so the
   *  picker still works in contexts without a draw log. */
  markedPerHero: {
    type: Object as PropType<Map<string, number>>,
    default: () => new Map<string, number>(),
  },
})

const emit = defineEmits<{
  (e: 'select', hero: Hero): void
  (e: 'edit-pool'): void
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

// Heroes that belong to this banner's pool. Falls back to CHT name lookup
// for override-added heroes whose name_jp is null.
const poolHeroes = computed<Hero[]>(() => {
  if (props.pool.length === 0) return []
  const poolSet = new Set(props.pool)
  return props.heroes.filter(h => {
    const key = h.name_jp || h.name
    return poolSet.has(key)
  })
})

const filteredHeroes = computed<Hero[]>(() => {
  const q = debouncedSearch.value.trim()
  if (!q) return poolHeroes.value
  return poolHeroes.value.filter(h => {
    if (h.name.includes(q)) return true
    if ((h.name_jp || '').includes(q)) return true
    return false
  })
})

const isHeroRare = (hero: Hero): boolean => {
  const key = hero.name_jp || hero.name
  return (props.markedPerHero.get(key) ?? 0) > 0
}

const onPick = (hero: Hero): void => {
  emit('select', hero)
}

const IMG_PLACEHOLDER =
  "data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 90 120'><rect width='90' height='120' fill='%23e5e7eb'/><text x='45' y='65' text-anchor='middle' font-family='sans-serif' font-size='10' fill='%239ca3af'>No%20Img</text></svg>"

const handleImageError = (e: Event) => {
  (e.target as HTMLImageElement).src = IMG_PLACEHOLDER
}
</script>
