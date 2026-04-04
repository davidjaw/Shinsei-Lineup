<template>
  <div class="flex flex-col h-full min-h-0">
    <!-- Filters -->
    <div class="p-2 border-b border-gray-100 space-y-2">
      <div class="flex justify-between items-center">
        <el-input 
          v-model="searchQuery" 
          placeholder="搜尋戰法名稱..." 
          clearable 
          prefix-icon="Search"
          class="flex-1 mr-2"
        />
        
        <el-switch 
          v-if="mode !== 'manage'"
          :model-value="filterOwned"
          @update:model-value="val => $emit('update:filterOwned', val)"
          inline-prompt 
          active-text="已擁有" 
          inactive-text="全部"
        />
        <div v-else class="text-xs font-bold text-gray-500 bg-gray-100 px-2 py-1 rounded">
           庫存編輯模式
        </div>
      </div>

      <div class="flex gap-2 overflow-x-auto pb-1">
        <el-select v-model="filterType" placeholder="類型" clearable class="w-28" size="small">
          <el-option label="指揮" value="指揮" />
          <!-- ... -->
          <el-option label="主動" value="主動" />
          <el-option label="突擊" value="突擊" />
          <el-option label="被動" value="被動" />
          <el-option label="兵種" value="兵種" />
          <el-option label="陣法" value="陣法" />
          <el-option label="內政" value="內政" />
        </el-select>
        <el-select v-model="filterRarity" placeholder="稀有度" clearable class="w-24" size="small">
          <el-option label="S" value="S" />
          <el-option label="A" value="A" />
          <el-option label="B" value="B" />
        </el-select>
      </div>
    </div>

    <!-- List -->
    <div class="flex-1 overflow-y-auto p-2" v-loading="loading">
       <div v-if="filteredSkills.length === 0" class="text-center py-10 text-gray-400">
        無符合條件的戰法
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
          :title="skill.unique_hero ? `${skill.name} (${skill.unique_hero})` : skill.name"
        >
          <template #reference>
            <div
              class="p-3 border border-gray-100 rounded-lg flex items-center gap-3 transition-colors relative bg-white cursor-help"
              :class="{
                'bg-gray-50 opacity-60 cursor-not-allowed': isUsed(skill) || isFixed(skill),
                'grayscale opacity-60': mode === 'manage' && !ownedSkills.includes(skill.name),
                'hover:border-indigo-300 hover:shadow-sm': isSelectable(skill)
              }"
              :draggable="isSelectable(skill)"
              @dragstart="(e) => handleDragStart(e, skill)"
              @click="handleSelect(skill)"
            >
              <img :src="skill.icon" class="w-10 h-10 rounded-lg bg-gray-200 object-cover flex-shrink-0" :class="{ 'grayscale': isUsed(skill) || isFixed(skill) }" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-bold text-gray-800">{{ skill.name }}</span>
                  <span class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ skill.type }}</span>
                  <span v-if="skill.rarity === 'S'" class="text-xs font-bold text-yellow-600">S</span>
                  <span v-if="isUsed(skill)" class="text-[10px] bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded font-bold">已裝備</span>
                  <span v-if="isFixed(skill)" class="text-[10px] bg-purple-200 text-purple-700 px-1.5 py-0.5 rounded font-bold">固有</span>
                  <span v-if="mode === 'manage' && !ownedSkills.includes(skill.name)" class="text-[10px] bg-black/70 text-white px-1.5 py-0.5 rounded">未擁有</span>
                </div>
                <BriefDescription v-if="skill.brief_description" :text="skill.brief_description" class="text-xs mt-1" />
                <div v-else class="text-xs text-gray-500 mt-1 truncate">{{ skill.description || '暫無描述' }}</div>
                <!-- Tags in non-hover state -->
                <div v-if="skill.tags?.length" class="flex flex-wrap gap-1 mt-1">
                  <span v-for="tag in skill.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1 rounded border border-blue-100">{{ tag }}</span>
                </div>
              </div>
            </div>
          </template>

          <!-- Popover Content: Use SkillDescription -->
          <div class="text-xs space-y-2">
            <div class="flex justify-between items-start">
              <div class="font-bold text-indigo-600 flex flex-col">
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
import { ref, computed, PropType, watch, onMounted } from 'vue'
import { useData } from '../composables/useData'
import SkillDescription from './SkillDescription.vue'
import BriefDescription from './BriefDescription.vue'

console.log('SkillLibrary.vue - script loading...')

const props = defineProps({
  mode: { type: String as PropType<'browse' | 'select' | 'manage'>, default: 'browse' }, // 'browse' | 'select' | 'manage'
  usedSkills: { type: Object as PropType<Set<string> | string[]>, default: () => [] },
  ownedSkills: { type: Array as PropType<string[]>, default: () => [] },
  filterOwned: { type: Boolean, default: false }
})

const emit = defineEmits(['select', 'update:ownedSkills', 'update:filterOwned'])

const { skills, loading } = useData()
console.log('🔍 SkillLibrary - after useData(). skills.value:', skills.value?.length || 'undefined/null')

const skillsInitialized = computed(() => {
  const initialized = skills.value && Array.isArray(skills.value) && skills.value.length > 0
  console.log('🔍 skillsInitialized computed:', initialized, 'skills.value:', skills.value?.length)
  return initialized
})

onMounted(() => {
  console.log('🔍 SkillLibrary mounted. skills.value:', skills.value?.length)
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

const filterType = ref('')
const filterRarity = ref('')
const expandedSkill = ref<string | null>(null)
const longPressTimer = ref<any>(null)
const skillLibraryMaxLevel = ref(true)
const LONG_PRESS_DURATION = 500 // ms

const formatRate = (rateStr: string | undefined) => {
  if (!rateStr) return ''
  const RANGE_REGEX = /(\d+(?:\.\d+)?%?)\s*(?:->|to|→)\s*(\d+(?:\.\d+)?%?)/
  const match = rateStr.match(RANGE_REGEX)
  if (match) {
    return skillLibraryMaxLevel.value ? match[2] : match[1]
  }
  return rateStr
}

console.log('🔍 Creating refs - expandedSkill:', expandedSkill, 'longPressTimer:', longPressTimer)

const startLongPress = (skillName: string) => {
  console.log('🔍 startLongPress called with:', skillName)
  if (longPressTimer.value) clearTimeout(longPressTimer.value)
  longPressTimer.value = setTimeout(() => {
    console.log('🔍 Setting expandedSkill to:', skillName)
    expandedSkill.value = skillName
  }, LONG_PRESS_DURATION)
}

const cancelLongPress = () => {
  console.log('🔍 cancelLongPress called')
  if (longPressTimer.value) {
    clearTimeout(longPressTimer.value)
    longPressTimer.value = null
  }
}

const handleDragStart = (event: DragEvent, skill: any) => {
  if (event.dataTransfer) {
    event.dataTransfer.setData('application/json', JSON.stringify(skill))
    event.dataTransfer.effectAllowed = 'copy'
  }
}

const filteredSkills = computed(() => {
  if (!skills.value || !Array.isArray(skills.value)) return []

  return skills.value.filter(s => {
    if (!s?.name) return false
    if (s.is_fixed) return false

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
    if (props.mode === 'manage' || skill.rarity !== 'S') return false

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

const handleSelect = (skill: any) => {
  if (!skill) return

  if (props.mode === 'manage') {
    toggleOwned(skill.name)
    return
  }

  // Cannot select if already used or is fixed skill
  if (!isSelectable(skill)) return

  // Don't select if detail panel is expanded
  if (expandedSkill.value && expandedSkill.value === skill.name) return

  emit('select', skill)
}
</script>

<style scoped>
.expand-enter-active, .expand-leave-active {
  transition: all 200ms ease;
}

.expand-enter-from {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to {
  opacity: 1;
  max-height: 500px;
}

.expand-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
