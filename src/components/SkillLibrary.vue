<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- Filters -->
    <div class="p-0 md:p-2 border-b border-gray-100 space-y-1 md:space-y-2">
      <div class="flex justify-between items-center px-1 md:px-0 pt-1 md:pt-0">
        <el-input
          v-model="searchQuery"
          placeholder="搜尋戰法名稱..."
          clearable
          prefix-icon="Search"
          class="flex-1 mr-1 md:mr-2"
          size="small"
        />
        
        <button
          v-if="mode === 'manage'"
          class="px-2 py-1 text-xs rounded border mr-2 transition-colors flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
          :class="allFilteredOwned
            ? 'bg-amber-500 text-white border-amber-500 hover:bg-amber-600'
            : 'bg-white text-gray-600 border-gray-300 hover:border-amber-500 hover:text-amber-600'"
          :disabled="filteredSkills.length === 0"
          :title="allFilteredOwned ? '取消勾選所有篩選結果' : '勾選所有篩選結果為已擁有'"
          @click="toggleSelectAllFiltered"
        >
          {{ allFilteredOwned ? '取消全選' : '全選' }}
        </button>
        <div v-if="mode === 'manage'" class="text-xs font-bold text-gray-500 bg-gray-100 px-2 py-1 rounded">
           庫存編輯模式
        </div>
      </div>

      <div class="flex gap-1 md:gap-2 overflow-x-auto pb-1 px-1 md:px-0">
        <el-select v-model="filterType" placeholder="類型" clearable class="w-28" size="small">
          <el-option v-for="type in typeChoices" :key="type" :label="type" :value="type" />
        </el-select>
        <el-select v-model="filterRarity" placeholder="稀有度" clearable class="w-24" size="small">
          <el-option v-for="rarity in rarityChoices" :key="rarity" :label="rarity" :value="rarity" />
        </el-select>
      </div>
    </div>

    <!-- List -->
    <div class="flex-1 overflow-y-auto p-0 md:p-2">
       <div v-if="filteredSkills.length === 0" class="text-center py-10">
        <template v-if="mode === 'select' && filterOwned && ownedSkills.length === 0">
          <p class="text-gray-400">庫存沒有戰法</p>
          <el-button type="primary" plain class="!mt-3 !rounded-sm" @click="emit('edit-inventory')">
            編輯庫存
          </el-button>
        </template>
        <p v-else class="text-gray-400">無符合條件的戰法</p>
      </div>
      <div
        :class="mode === 'manage' ? 'grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2' : 'flex flex-col'"
      >
        <!-- Skill Items with Popover -->
        <el-popover
          v-for="skill in filteredSkills"
          :key="skill.name"
          placement="left"
          :width="280"
          trigger="hover"
          :title="skill.unique_hero ? `${skill.name} (${localizeHero(skill.unique_hero)})` : skill.name"
        >
          <template #reference>
            <div
              class="p-1.5 md:p-3 border border-gray-100 rounded-lg flex items-center gap-1.5 md:gap-3 transition-colors relative bg-white cursor-help"
              :class="{
                'bg-gray-50 opacity-60 cursor-not-allowed': isUsed(skill) || isFixed(skill),
                'grayscale opacity-60': mode === 'manage' && !ownedSkills.includes(skill.name),
                'hover:border-indigo-300 hover:shadow-sm': isSelectable(skill)
              }"
              :draggable="isSelectable(skill)"
              @dragstart="(e) => handleDragStart(e, skill)"
              @dragend="emit('skill-drag-end')"
              @click="handleSelect(skill)"
            >
              <SkillTypeMark
                :type="skill.type"
                size="list"
                :muted="isUsed(skill) || isFixed(skill)"
              />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1 md:gap-2 flex-wrap">
                  <span class="font-bold text-gray-800 text-xs md:text-base">{{ skill.name }}</span>
                  <span class="text-[9px] md:text-xs px-1 md:px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ skill.type }}</span>
                  <span v-if="skill.rarity === 'S'" class="text-[9px] md:text-xs font-bold text-yellow-600">S</span>
                  <span v-if="isUsed(skill)" class="text-[9px] md:text-[10px] bg-gray-200 text-gray-600 px-1 md:px-1.5 py-0.5 rounded font-bold">已裝備</span>
                  <span v-if="isFixed(skill)" class="text-[9px] md:text-[10px] bg-purple-200 text-purple-700 px-1 md:px-1.5 py-0.5 rounded font-bold">固有</span>
                  <span v-if="mode === 'manage' && !ownedSkills.includes(skill.name)" class="text-[9px] md:text-[10px] bg-black/70 text-white px-1 md:px-1.5 py-0.5 rounded">未擁有</span>
                  <span
                    v-if="skill.is_event_skill"
                    class="ml-auto text-[9px] md:text-[10px] text-gray-400 truncate text-right"
                  >事件戰法</span>
                  <span
                    v-else-if="!isFixed(skill) && teachersBySkill.get(skill.name)?.length"
                    class="ml-auto text-[9px] md:text-[10px] text-gray-400 truncate text-right"
                    :title="'傳授: ' + teachersBySkill.get(skill.name)!.join('、')"
                  >傳授: {{ teachersBySkill.get(skill.name)!.join('、') }}</span>
                </div>
                <BriefDescription v-if="skill.brief_description" :text="skill.brief_description" :vars="skill.vars" class="text-[10px] md:text-xs mt-0.5 md:mt-1" />
                <div v-else class="text-[10px] md:text-xs text-gray-500 mt-0.5 md:mt-1 truncate">{{ skill.description || '暫無描述' }}</div>
                <!-- Tags in non-hover state -->
                <div v-if="skill.tags?.length" class="flex flex-wrap gap-0.5 md:gap-1 mt-0.5 md:mt-1">
                  <span v-for="tag in skill.tags" :key="tag" class="text-[9px] md:text-[10px] bg-blue-50 text-blue-600 px-1 rounded border border-blue-100">{{ tag }}</span>
                </div>
              </div>
            </div>
          </template>

          <!-- Popover Content: Use SkillDescription -->
          <div class="text-xs space-y-2">
            <div class="flex justify-between items-start">
              <div class="font-bold text-focus flex flex-col">
                <span>{{ skill.type }}</span>
                <span v-if="skill.activation_rate" class="text-[10px] text-gray-500 mt-0.5">
                  發動機率 {{ formatRate(skill.activation_rate) }}
                </span>
              </div>
              <div class="flex items-center gap-1 scale-90 origin-top-right">
                <span class="text-[10px] text-gray-400">滿級</span>
                <el-switch v-model="skillLibraryMaxLevel" size="small" />
              </div>
            </div>
            <SkillDescription
              :description="skill.description"
              :commander-description="skill.commander_description"
              :is-max-level="skillLibraryMaxLevel"
              :vars="skill.vars"
            />
          </div>
          <div v-if="skill.target" class="text-xs text-gray-400 italic mt-2">目標: {{ skill.target }}</div>
          <div v-if="skill.tags?.length" class="flex flex-wrap gap-1 mt-2">
            <span v-for="tag in skill.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-100">{{ tag }}</span>
          </div>
          <div class="text-[10px] opacity-80 border-t pt-2 mt-2 border-gray-300 text-gray-600">
            {{ isFixed(skill) ? '固有戰法 (不可配置)' : isUsed(skill) ? '已裝備 (不可重複)' : '可配置' }}
          </div>
        </el-popover>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, PropType, watch } from 'vue'
import { useData } from '../composables/useData'
import { TRANSPARENT_GIF, formatRate as _formatRate, isEquippableSkillType } from '../constants/gameData'
import SkillDescription from './SkillDescription.vue'
import BriefDescription from './BriefDescription.vue'
import SkillTypeMark from './SkillTypeMark.vue'
import { gameSeasonOffer, offeredSkills } from '../lib/gameSeasonMisfits'

const props = defineProps({
  mode: { type: String as PropType<'browse' | 'select' | 'manage'>, default: 'browse' }, // 'browse' | 'select' | 'manage'
  usedSkills: { type: Object as PropType<Set<string> | string[]>, default: () => [] },
  ownedSkills: { type: Array as PropType<string[]>, default: () => [] },
  filterOwned: { type: Boolean, default: false },
  // The lineup page's game season: only what it offers is listed, and only the types and rarities that list has are
  // offered as filters. Absent, every season's.
  gameSeason: { type: String as PropType<string | null>, default: null },
})

const emit = defineEmits(['select', 'update:ownedSkills', 'skill-drag-start', 'skill-drag-end', 'edit-inventory'])

const { skills, heroes } = useData()

const teachersBySkill = computed(() => {
  const map = new Map<string, string[]>()
  for (const h of heroes.value || []) {
    if (!h.teachable_skill) continue
    const arr = map.get(h.teachable_skill) || []
    arr.push(h.name)
    map.set(h.teachable_skill, arr)
  }
  return map
})

const jpToCht = computed(() => {
  const map = new Map<string, string>()
  for (const h of heroes.value || []) {
    if (h.name_jp) map.set(h.name_jp, h.name)
  }
  return map
})

const localizeHero = (jp?: string | null) => (jp && jpToCht.value.get(jp)) || jp || ''

const searchQuery = ref('')
const debouncedSearchQuery = ref('')
let debounceTimer: any = null

watch(searchQuery, (newVal) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debouncedSearchQuery.value = newVal
  }, 200)
})

const filterType = ref('')
const filterRarity = ref('')
const skillLibraryMaxLevel = ref(true)

const formatRate = (rateStr: string | undefined) => _formatRate(rateStr, skillLibraryMaxLevel.value)

const handleDragStart = (event: DragEvent, skill: any) => {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/json', JSON.stringify(skill))
    event.dataTransfer.effectAllowed = 'copy'
    const ghost = new Image()
    ghost.src = TRANSPARENT_GIF
    event.dataTransfer.setDragImage(ghost, 0, 0)
  }
  emit('skill-drag-start', skill)
}

const SKILL_TYPES = ['指揮', '主動', '突擊', '被動', '兵種', '陣法']
const RARITIES = ['S', 'A', 'B']

// The equippable skills the game season offers: what the list and its filter choices are drawn from.
const pool = computed(() => {
  if (!skills.value || !Array.isArray(skills.value)) return []
  const offer = props.gameSeason ? gameSeasonOffer(props.gameSeason, heroes.value) : null
  return offeredSkills(skills.value, offer).filter(s => s?.name && !s.is_fixed && isEquippableSkillType(s.type))
})
const typeChoices = computed(() => SKILL_TYPES.filter(type => pool.value.some(s => s.type === type)))
const rarityChoices = computed(() => RARITIES.filter(rarity => pool.value.some(s => s.rarity === rarity)))

// A chosen type or rarity the new season does not have would hide everything: start over.
watch(() => props.gameSeason, () => {
  filterType.value = ''
  filterRarity.value = ''
})

const filteredSkills = computed(() => {
  return pool.value.filter(s => {
    if (debouncedSearchQuery.value && !s.name.includes(debouncedSearchQuery.value)) return false
    if (filterType.value && s.type !== filterType.value) return false
    if (filterRarity.value && s.rarity !== filterRarity.value) return false
    if (props.mode !== 'manage' && props.filterOwned && !props.ownedSkills.includes(s.name)) return false

    return true
  })
})

const isUsed = (skill: any) => {
  try {
    if (!skill || !skill.name) return false

    // Only applicable in select/browse mode
    if (props.mode === 'manage') return false

    if (Array.isArray(props.usedSkills)) {
      return props.usedSkills.includes(skill.name)
    }
    return (props.usedSkills as Set<string>).has(skill.name)
  } catch (e) {
    console.error('🔴 isUsed error:', e, 'skill:', skill)
    return false
  }
}

const isFixed = (skill: any) => {
  try {
    if (!skill) return false
    // Fixed/unique skills cannot be selected
    return skill.is_fixed === true
  } catch (e) {
    console.error('🔴 isFixed error:', e, 'skill:', skill)
    return false
  }
}

const isSelectable = (skill: any) => {
  try {
    if (!skill) return false
    // Cannot select if already used (S-rank) or is fixed skill
    return !isUsed(skill) && !isFixed(skill)
  } catch (e) {
    console.error('🔴 isSelectable error:', e, 'skill:', skill)
    return false
  }
}

const toggleOwned = (name: string) => {
  const newOwned = [...props.ownedSkills]
  if (newOwned.includes(name)) {
    newOwned.splice(newOwned.indexOf(name), 1)
  } else {
    newOwned.push(name)
  }
  emit('update:ownedSkills', newOwned)
}

// Select-all toggle for manage mode — scopes to the current filter (search +
// type + rarity). Same toggle behavior as HeroLibrary.
const allFilteredOwned = computed(() =>
  filteredSkills.value.length > 0 &&
  filteredSkills.value.every(s => props.ownedSkills.includes(s.name))
)

const toggleSelectAllFiltered = () => {
  const filteredNames = filteredSkills.value.map(s => s.name)
  if (allFilteredOwned.value) {
    const filteredSet = new Set(filteredNames)
    emit('update:ownedSkills', props.ownedSkills.filter(n => !filteredSet.has(n)))
  } else {
    const ownedSet = new Set(props.ownedSkills)
    const newOwned = [...props.ownedSkills]
    for (const n of filteredNames) if (!ownedSet.has(n)) newOwned.push(n)
    emit('update:ownedSkills', newOwned)
  }
}

const handleSelect = (skill: any) => {
  if (!skill) return

  if (props.mode === 'manage') {
    toggleOwned(skill.name)
    return
  }

  // Cannot select if already used or is fixed skill
  if (!isSelectable(skill)) return

  emit('select', skill)
}
</script>

