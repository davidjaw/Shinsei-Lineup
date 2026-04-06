<template>
  <div class="bg-white rounded-md shadow-sm border border-gray-200 p-0.5 md:p-2 flex flex-col gap-0.5 md:gap-2 h-full relative">
    <!-- Role Header -->
    <div class="flex items-center justify-between border-b border-gray-100 pb-0.5 md:pb-2 px-1 md:px-0">
      <span class="font-bold text-gray-700 text-[10px] md:text-base">{{ title }}</span>
      <div class="flex items-center">
        <!-- Swap Button (Mobile Only) -->
        <el-button v-if="hero" link size="small"
          class="md:hidden !p-0 !h-auto mr-1"
          :class="isSwapSource ? 'text-indigo-500' : 'text-gray-400'"
          @click.stop="$emit('swap-click')"
        >
          <el-icon><Sort /></el-icon>
        </el-button>
        <!-- Info Button (Mobile Only) -->
        <el-button v-if="hero" link size="small" class="md:hidden !p-0 !h-auto mr-1" @click.stop="$emit('open-detail')">
           <el-icon class="text-indigo-400"><InfoFilled /></el-icon>
        </el-button>
        <el-button v-if="hero" type="danger" link size="small" class="!p-0 !h-auto" @click="removeHero">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- Hero Slot -->
    <div
      class="rounded border-2 border-dashed flex items-center justify-center cursor-pointer transition-all relative overflow-hidden group w-full aspect-[3/4] md:order-1"
      :class="isDragTarget
        ? 'border-indigo-400 bg-indigo-50 scale-[1.02] shadow-md shadow-indigo-200'
        : isSwapSource
          ? 'border-indigo-500 ring-2 ring-indigo-500 border-gray-200'
          : swapModeActive
            ? 'border-indigo-300 ring-2 ring-indigo-200'
            : 'border-gray-200 hover:border-indigo-300'"
      :draggable="!!hero"
      @click="$emit('open-hero-select')"
      @dragstart="handleHeroDragStart"
      @dragend="$emit('hero-drag-end')"
      @dragover.prevent
      @drop.prevent="handleHeroDropEvent"
    >
      <div v-if="isDragTarget" class="absolute inset-0 flex flex-col items-center justify-center z-10 bg-indigo-50/60 pointer-events-none">
        <el-icon class="text-indigo-400 text-xl md:text-3xl"><Sort /></el-icon>
        <span class="text-indigo-500 text-[8px] md:text-xs mt-1 font-medium">放置交換</span>
      </div>
      <HeroCard v-if="hero" :hero="hero" class="w-full h-full border-none shadow-none pointer-events-none" />
      <div v-else class="text-gray-400 flex flex-col items-center py-2 md:py-10">
        <el-icon :size="16" class="md:text-3xl"><Plus /></el-icon>
        <span class="text-[9px] md:text-xs mt-0.5">選擇</span>
      </div>
    </div>

    <!-- Stats & Traits Area (Only when hero exists) -->
    <div v-if="hero" class="relative -mt-2 mb-1 md:mb-2 z-10 flex items-center gap-1 md:gap-3 px-1 md:px-2 justify-between md:justify-start md:order-3">
      <!-- Radar Chart (Desktop Only) -->
      <el-popover
        placement="right"
        :width="200"
        trigger="hover"
      >
        <template #reference>
          <div 
            class="hidden md:block bg-white rounded-full p-0.5 md:p-1 shadow-md border border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors group flex-shrink-0"
            @click.stop="openStatsEditor"
          >
            <RadarChart :stats="stats" :base-stats="heroBaseStats" :size="90" />
          </div>
        </template>
        
        <!-- Popover Content -->
        <div class="space-y-2">
          <div class="text-xs font-bold text-gray-500 border-b pb-1 mb-1">屬性總覽 (基礎+自由加點)</div>
          <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div v-for="(label, key) in statLabels" :key="key" class="flex justify-between">
              <span class="text-gray-600">{{ label }}</span>
              <span>
                <span class="font-bold text-gray-800">{{ heroBaseStats[key] }}</span>
                <span v-if="statBonus[key] > 0" class="text-green-600 ml-0.5">+{{ statBonus[key] }}</span>
                <span v-else-if="statBonus[key] < 0" class="text-red-500 ml-0.5">{{ statBonus[key] }}</span>
              </span>
            </div>
          </div>
          <div class="text-[10px] text-gray-400 mt-1">剩餘自由點: {{ freePointsRemaining }}</div>
          <div class="text-[10px] text-indigo-500 text-right italic">
            <el-icon class="align-middle mr-0.5"><Edit /></el-icon>點擊圖表調整
          </div>
        </div>
      </el-popover>

      <!-- Traits List (Right) -->
      <div class="flex-1 flex flex-col gap-0.5 md:gap-1 min-w-0">
        <span class="hidden md:block text-[10px] font-bold text-gray-500 ml-1">特性:</span>
        <div class="grid grid-cols-2 md:grid-cols-2 gap-0.5 md:gap-1.5 w-full">
          <el-tooltip
            v-for="(trait, idx) in localTraits" 
            :key="idx"
            placement="top"
            :show-after="300"
          >
            <template #content>
              <div class="max-w-[200px]">
                <div class="font-bold mb-1">{{ trait.name }}</div>
                <div class="text-xs mb-2">{{ resolveTraitDesc(trait) }}</div>
                <div class="text-[10px] opacity-80 border-t pt-1 border-gray-500">
                  {{ trait.name === '固有' ? '固有特性 (不可變更)' : trait.active ? '點擊停用' : '點擊啟用' }}
                </div>
              </div>
            </template>
            <div 
              class="rounded px-0.5 md:px-2 py-0.5 md:py-1 text-[9px] md:text-xs text-center border cursor-pointer transition-all select-none truncate"
              :class="[
                getTraitColor(trait.rank),
                { 'opacity-50 saturate-50 scale-95': !trait.active, 'ring-1 ring-offset-1 ring-gray-200': !trait.active }
              ]"
              @click.stop="toggleTrait(idx)"
            >
              {{ trait.name }}
            </div>
          </el-tooltip>
        </div>
      </div>
    </div>
    
    <!-- Equip Traits List (Add-on) -->
    <div v-if="hero" class="mb-1 md:mb-2 px-1 md:px-2 md:order-4 md:grid md:grid-cols-2 md:gap-2 md:items-start">
       <span class="text-[10px] font-bold text-gray-500 ml-1 mb-1 md:col-span-2 md:mb-0.5">裝備特性:</span>
       <div class="grid grid-cols-4 md:grid-cols-4 gap-0.5 md:gap-1 md:col-span-2">
          <div
            v-for="(trait, idx) in equipTraits || [null, null, null, null]"
            :key="'eq'+idx"
            class="rounded px-0.5 md:px-1 py-0.5 md:py-0.5 text-[8px] md:text-[9px] text-center border border-dashed cursor-pointer transition-all select-none truncate hover:border-indigo-300 hover:bg-indigo-50 min-h-6 md:min-h-7 flex items-center justify-center"
            :class="trait ? getTraitColor(trait.rank) + ' border-solid' : 'border-gray-300 text-gray-400'"
            @click.stop="openEquipTraitSelect(idx)"
          >
            {{ trait ? trait.name : '+' }}
          </div>
       </div>
    </div>

    <!-- Skills Area -->
    <div class="flex flex-col gap-0.5 md:gap-2 md:order-2 md:flex-1 md:min-h-0">
      <!-- Unique Skill (Auto-filled) -->
      <el-popover
        placement="top"
        :title="hero?.unique_skill || '---'"
        :width="240"
        trigger="hover"
        :disabled="!hero?.unique_skill"
      >
        <template #reference>
          <div class="flex items-center gap-1 md:gap-2 p-0.5 md:p-2 bg-gray-50 rounded border border-gray-100 opacity-80">
            <div class="w-5 h-5 md:w-8 md:h-8 bg-yellow-100 rounded flex items-center justify-center text-[9px] md:text-xs font-bold text-yellow-700 flex-shrink-0">
              主
            </div>
            <div class="flex-1 min-w-0">
              <!-- Name + Tags on same line -->
              <div class="flex items-center gap-1 mb-0.5">
                <div class="text-[9px] md:text-sm text-gray-600 truncate">{{ hero?.unique_skill || '---' }}</div>
                <div v-if="uniqueSkillData?.tags?.length" class="flex gap-0.5">
                  <span v-for="tag in uniqueSkillData.tags.slice(0, 2)" :key="tag" class="text-[7px] md:text-[8px] bg-blue-50 text-blue-600 px-0.5 rounded border border-blue-100 flex-shrink-0">{{ tag }}</span>
                </div>
              </div>
              <!-- Brief Description in larger font -->
              <BriefDescription v-if="uniqueSkillData?.brief_description" :text="uniqueSkillData.brief_description" class="text-[9px] md:text-sm italic" />
            </div>
          </div>
        </template>
        <div v-if="uniqueSkillData" class="text-xs space-y-2">
           <div class="flex justify-between items-start">
             <div class="font-bold text-indigo-600 flex flex-col">
                <span>{{ uniqueSkillData.type }}</span>
                <span v-if="uniqueSkillData.activation_rate" class="text-[10px] text-gray-500 mt-0.5">
                   發動機率 {{ formatRate(uniqueSkillData.activation_rate) }}
                </span>
             </div>
             <div class="flex items-center gap-1 scale-90 origin-top-right">
                <span class="text-[10px] text-gray-400">滿級</span>
                <el-switch v-model="isMaxLevel" size="small" />
             </div>
          </div>
          <SkillDescription
            :description="uniqueSkillData.description"
            :commander-description="uniqueSkillData.commander_description"
            :is-max-level="isMaxLevel"
            :vars="uniqueSkillData.vars"
          />
          <div v-if="uniqueSkillData.target" class="text-xs text-gray-400 italic mt-2">目標: {{ uniqueSkillData.target }}</div>
          <div v-if="uniqueSkillData.tags?.length" class="flex flex-wrap gap-1 mt-2">
            <span v-for="tag in uniqueSkillData.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-100">{{ tag }}</span>
          </div>
        </div>
        <div v-else class="text-xs text-gray-500">
          <p>此武將的專屬固有戰法（資料庫中未找到詳細資訊）。</p>
        </div>
      </el-popover>

      <!-- Learnable Slot 1 -->
      <el-popover
        placement="top"
        :title="skill1?.name"
        :width="240"
        trigger="hover"
        :disabled="!skill1 || skillDragging"
      >
        <template #reference>
          <div
            class="flex items-center gap-1 md:gap-2 p-0.5 md:p-2 bg-white rounded border cursor-pointer transition-all"
            :class="[
              draggingSlot === 1 ? 'opacity-0' : '',
              focusedSkillSlot === 1
                ? 'ring-1 md:ring-2 ring-indigo-500 bg-indigo-50 border-indigo-500'
                : dragOverSlot === 1
                  ? 'border-indigo-500 bg-indigo-100 ring-2 ring-indigo-400 scale-[1.02]'
                  : skillDragging
                    ? 'border-dashed border-indigo-300 bg-indigo-50'
                    : 'border-gray-200 hover:border-indigo-400'
            ]"
            :draggable="!!skill1"
            @click="$emit('open-skill-select', 1)"
            @dragstart="(e) => handleSkillDragStart(e, 1)"
            @dragend="draggingSlot = null; emit('skill-drag-end')"
            @dragover.prevent
            @dragenter="dragOverSlot = 1"
            @dragleave="(e) => { if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) dragOverSlot = null }"
            @drop="(e) => { dragOverSlot = null; handleDrop(e, 1) }"
          >
            <img v-if="skill1" :src="skill1.icon" class="w-5 h-5 md:w-8 md:h-8 rounded bg-gray-200 object-cover flex-shrink-0" />
            <div v-else class="w-5 h-5 md:w-8 md:h-8 bg-gray-100 rounded flex items-center justify-center text-gray-400 flex-shrink-0">
              <el-icon class="text-[10px] md:text-base"><Plus /></el-icon>
            </div>
            
            <div class="flex-1 min-w-0">
              <!-- Name + Tags on same line -->
              <div class="flex items-center gap-1 mb-0.5">
                <div v-if="skill1" class="text-[9px] md:text-sm font-bold text-gray-800 truncate">{{ skill1.name }}</div>
                <div v-else class="text-[9px] md:text-sm text-gray-400">習得</div>
                <div v-if="skill1?.tags?.length" class="flex gap-0.5">
                  <span v-for="tag in skill1.tags.slice(0, 2)" :key="tag" class="text-[7px] md:text-[8px] bg-blue-50 text-blue-600 px-0.5 rounded border border-blue-100 flex-shrink-0">{{ tag }}</span>
                </div>
              </div>
              <!-- Brief Description in larger font -->
              <BriefDescription v-if="skill1?.brief_description" :text="skill1.brief_description" class="text-[9px] md:text-sm italic" />
            </div>
            <el-button v-if="skill1" link type="danger" size="small" class="!p-0 !h-auto" @click.stop="$emit('update:skill1', null)">
                <el-icon :size="10"><Close /></el-icon>
            </el-button>
          </div>
        </template>
        <div v-if="skill1" class="text-xs space-y-2">
          <div class="flex justify-between items-start">
             <div class="font-bold text-indigo-600 flex flex-col">
                <span>{{ skill1.type }}</span>
                <span v-if="skill1.activation_rate" class="text-[10px] text-gray-500 mt-0.5">
                  發動機率 {{ formatRate(skill1.activation_rate) }}
                </span>
             </div>
             <div class="flex items-center gap-1 scale-90 origin-top-right">
                <span class="text-[10px] text-gray-400">滿級</span>
                <el-switch v-model="isMaxLevel" size="small" />
             </div>
          </div>
          <SkillDescription
            :description="skill1.description"
            :commander-description="skill1.commander_description"
            :is-max-level="isMaxLevel"
            :vars="skill1.vars"
          />
          <div v-if="skill1.target" class="text-xs text-gray-400 italic mt-2">目標: {{ skill1.target }}</div>
          <div v-if="skill1.tags?.length" class="flex flex-wrap gap-1 mt-2">
            <span v-for="tag in skill1.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-100">{{ tag }}</span>
          </div>
        </div>
      </el-popover>

      <!-- Learnable Slot 2 -->
      <el-popover
        placement="top"
        :title="skill2?.name"
        :width="240"
        trigger="hover"
        :disabled="!skill2 || skillDragging"
      >
        <template #reference>
          <div
            class="flex items-center gap-1 md:gap-2 p-0.5 md:p-2 bg-white rounded border cursor-pointer transition-all"
            :class="[
              draggingSlot === 2 ? 'opacity-0' : '',
              focusedSkillSlot === 2
                ? 'ring-1 md:ring-2 ring-indigo-500 bg-indigo-50 border-indigo-500'
                : dragOverSlot === 2
                  ? 'border-indigo-500 bg-indigo-100 ring-2 ring-indigo-400 scale-[1.02]'
                  : skillDragging
                    ? 'border-dashed border-indigo-300 bg-indigo-50'
                    : 'border-gray-200 hover:border-indigo-400'
            ]"
            :draggable="!!skill2"
            @click="$emit('open-skill-select', 2)"
            @dragstart="(e) => handleSkillDragStart(e, 2)"
            @dragend="draggingSlot = null; emit('skill-drag-end')"
            @dragover.prevent
            @dragenter="dragOverSlot = 2"
            @dragleave="(e) => { if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) dragOverSlot = null }"
            @drop="(e) => { dragOverSlot = null; handleDrop(e, 2) }"
          >
            <img v-if="skill2" :src="skill2.icon" class="w-5 h-5 md:w-8 md:h-8 rounded bg-gray-200 object-cover flex-shrink-0" />
            <div v-else class="w-5 h-5 md:w-8 md:h-8 bg-gray-100 rounded flex items-center justify-center text-gray-400 flex-shrink-0">
              <el-icon class="text-[10px] md:text-base"><Plus /></el-icon>
            </div>
            
            <div class="flex-1 min-w-0">
              <!-- Name + Tags on same line -->
              <div class="flex items-center gap-1 mb-0.5">
                <div v-if="skill2" class="text-[9px] md:text-sm font-bold text-gray-800 truncate">{{ skill2.name }}</div>
                <div v-else class="text-[9px] md:text-sm text-gray-400">習得</div>
                <div v-if="skill2?.tags?.length" class="flex gap-0.5">
                  <span v-for="tag in skill2.tags.slice(0, 2)" :key="tag" class="text-[7px] md:text-[8px] bg-blue-50 text-blue-600 px-0.5 rounded border border-blue-100 flex-shrink-0">{{ tag }}</span>
                </div>
              </div>
              <!-- Brief Description in larger font -->
              <BriefDescription v-if="skill2?.brief_description" :text="skill2.brief_description" class="text-[9px] md:text-sm italic" />
            </div>
             <el-button v-if="skill2" link type="danger" size="small" class="!p-0 !h-auto" @click.stop="$emit('update:skill2', null)">
                <el-icon :size="10"><Close /></el-icon>
            </el-button>
          </div>
        </template>
        <div v-if="skill2" class="text-xs space-y-2">
          <div class="flex justify-between items-start">
             <div class="font-bold text-indigo-600 flex flex-col">
                <span>{{ skill2.type }}</span>
                <span v-if="skill2.activation_rate" class="text-[10px] text-gray-500 mt-0.5">
                  發動機率 {{ formatRate(skill2.activation_rate) }}
                </span>
             </div>
             <div class="flex items-center gap-1 scale-90 origin-top-right">
                <span class="text-[10px] text-gray-400">滿級</span>
                <el-switch v-model="isMaxLevel" size="small" />
             </div>
          </div>
          <SkillDescription
            :description="skill2.description"
            :commander-description="skill2.commander_description"
            :is-max-level="isMaxLevel"
            :vars="skill2.vars"
          />
          <div v-if="skill2.target" class="text-xs text-gray-400 italic mt-2">目標: {{ skill2.target }}</div>
          <div v-if="skill2.tags?.length" class="flex flex-wrap gap-1 mt-2">
            <span v-for="tag in skill2.tags" :key="tag" class="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded border border-blue-100">{{ tag }}</span>
          </div>
        </div>
      </el-popover>
    </div>

    <!-- Stats Editor Dialog -->
    <el-dialog v-model="statsDialogVisible" title="自由屬性加點" width="360px" append-to-body align-center>
      <div class="flex flex-col gap-3">
        <div class="text-xs text-gray-500 flex justify-between">
          <span>剩餘可分配點數</span>
          <span class="font-bold" :class="localFreeRemaining < 0 ? 'text-red-500' : 'text-indigo-600'">{{ localFreeRemaining }} / 50</span>
        </div>
        <div class="space-y-2">
          <div v-for="(label, key) in statLabels" :key="key" class="flex items-center gap-1.5">
            <div class="w-8 text-xs font-bold text-gray-600">{{ label }}</div>
            <div class="text-xs text-gray-400 w-8 text-right">{{ heroBaseStats[key] }}</div>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localBonus[key] <= -10"
              @click="adjustBonus(key, -10)">-10</button>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localBonus[key] <= 0"
              @click="adjustBonus(key, -1)">-</button>
            <div class="w-10 text-center text-xs font-bold" :class="localBonus[key] > 0 ? 'text-green-600' : localBonus[key] < 0 ? 'text-red-500' : 'text-gray-400'">
              {{ localBonus[key] > 0 ? '+' : '' }}{{ localBonus[key] }}
            </div>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localFreeRemaining <= 0"
              @click="adjustBonus(key, 1)">+</button>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localFreeRemaining < 10"
              @click="adjustBonus(key, 10)">+10</button>
            <div class="w-8 text-xs font-bold text-right text-gray-800">{{ heroBaseStats[key] + localBonus[key] }}</div>
          </div>
        </div>
        <button class="text-xs text-gray-400 hover:text-red-500 self-end" @click="resetBonus">重置</button>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="statsDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveStats">確認修改</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Equip Trait Select Dialog -->
    <el-dialog v-model="equipTraitDialogVisible" title="選擇裝備特性" width="300px" append-to-body align-center>
      <div class="grid grid-cols-2 gap-2">
        <div 
           v-for="opt in MOCK_EQUIP_TRAITS" 
           :key="opt.name"
           class="p-2 border rounded cursor-pointer hover:bg-gray-50 text-center text-xs"
           @click="selectEquipTrait(opt)"
        >
          <div class="font-bold text-gray-700">{{ opt.name }}</div>
          <div class="text-[10px] text-gray-500">{{ opt.description }}</div>
        </div>
         <div 
           class="p-2 border rounded cursor-pointer hover:bg-red-50 text-center text-xs text-red-500 border-red-100"
           @click="selectEquipTrait(null as any)"
        >
          移除
        </div>
      </div>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { PropType, ref, watch, computed } from 'vue'
import { Plus, Close, Edit, Setting, InfoFilled, Sort } from '@element-plus/icons-vue'
import HeroCard from './HeroCard.vue'
import RadarChart from './RadarChart.vue'
import SkillDescription from './SkillDescription.vue'
import BriefDescription from './BriefDescription.vue'
import { Hero, Skill, Trait, useData } from '../composables/useData'
import { useTemplateParser } from '../composables/useTemplateParser'

import { MOCK_EQUIP_TRAITS, TRANSPARENT_GIF, formatRate as _formatRate } from '../constants/gameData'

const props = defineProps({
  title: String,
  role: String,
  hero: Object as PropType<Hero | null>,
  skill1: Object as PropType<Skill | null>,
  skill2: Object as PropType<Skill | null>,
  stats: Object as PropType<any>,
  equipTraits: Array as PropType<Trait[]>,
  focusedSkillSlot: Number as PropType<number | null>,
  isSwapSource: { type: Boolean, default: false },
  swapModeActive: { type: Boolean, default: false },
  isDragTarget: { type: Boolean, default: false },
  skillDragging: { type: Boolean, default: false }
})

const { skills } = useData()
const { parseTextToPlain } = useTemplateParser()

const resolveTraitDesc = (trait: any) => {
  if (!trait?.description) return '說明: 尚未建立資料'
  return parseTextToPlain(trait.description, false, trait.vars)
}

const isMaxLevel = ref(true)
const dragOverSlot = ref<number | null>(null)
const draggingSlot = ref<number | null>(null)

const formatRate = (rateStr: string | undefined) => _formatRate(rateStr, isMaxLevel.value)

const uniqueSkillData = computed(() => {
  if (!props.hero?.unique_skill) return null
  const name = props.hero.unique_skill
  return skills.value.find(s => s.name === name || s.name_jp === name)
})

const emit = defineEmits([
  'update:hero', 
  'update:skill1', 
  'update:skill2',
  'update:stats',
  'update:equipTraits',
  'open-hero-select',
  'open-skill-select',
  'skill-drop',
  'open-detail',
  'swap-click',
  'hero-drag-start',
  'hero-drag-end',
  'hero-drop',
  'skill-drag-start',
  'skill-drag-end',
  'skill-slot-drop'
])

const removeHero = () => {
  emit('update:hero', null)
  emit('update:skill1', null)
  emit('update:skill2', null)
  emit('update:equipTraits', [])
  // Reset stats to default not handled here explicitly but usually desired
}

const handleHeroDragStart = (event: DragEvent) => {
  if (!props.hero) return
  event.dataTransfer?.setData('application/hero-role', props.role as string)
  event.dataTransfer!.effectAllowed = 'move'
  emit('hero-drag-start')
}

const handleHeroDropEvent = (event: DragEvent) => {
  if (event.dataTransfer?.types.includes('application/hero-role')) {
    emit('hero-drop')
  }
}

// Stats Editing
const FREE_POINTS_TOTAL = 50
const statsDialogVisible = ref(false)
const STAT_KEYS = ['lea', 'val', 'int', 'pol', 'cha', 'spd'] as const

const heroBaseStats = computed(() => {
  const s = props.hero?.stats
  return {
    lea: s?.lea ?? 0, val: s?.val ?? 0, int: s?.int ?? 0,
    pol: s?.pol ?? 0, cha: s?.cha ?? 0, spd: s?.spd ?? 0,
  }
})

const statBonus = computed(() => {
  const base = heroBaseStats.value
  const result: Record<string, number> = {}
  for (const k of STAT_KEYS) result[k] = (props.stats[k] ?? 0) - base[k]
  return result
})

const freePointsRemaining = computed(() => {
  let used = 0
  for (const k of STAT_KEYS) used += Math.max(0, statBonus.value[k])
  return FREE_POINTS_TOTAL - used
})

// Local editing state
const localBonus = ref<Record<string, number>>({})

const localFreeRemaining = computed(() => {
  let used = 0
  for (const k of STAT_KEYS) used += Math.max(0, localBonus.value[k] ?? 0)
  return FREE_POINTS_TOTAL - used
})

const openStatsEditor = () => {
  if (!props.hero) return
  const b: Record<string, number> = {}
  for (const k of STAT_KEYS) b[k] = statBonus.value[k]
  localBonus.value = b
  statsDialogVisible.value = true
}

const adjustBonus = (key: string, delta: number) => {
  const current = localBonus.value[key] ?? 0
  const newVal = current + delta
  // Can't go below 0 (no negative bonus)
  if (newVal < 0) return
  // Can't exceed remaining free points (for positive delta)
  if (delta > 0 && delta > localFreeRemaining.value) return
  localBonus.value[key] = newVal
}

const resetBonus = () => {
  for (const k of STAT_KEYS) localBonus.value[k] = 0
}

const saveStats = () => {
  const base = heroBaseStats.value
  const result: Record<string, number> = {}
  for (const k of STAT_KEYS) result[k] = base[k] + (localBonus.value[k] ?? 0)
  emit('update:stats', result)
  statsDialogVisible.value = false
}

const statLabels: Record<string, string> = {
  lea: '統帥',
  val: '武勇',
  int: '智略',
  pol: '政務',
  cha: '魅力',
  spd: '速度'
}

// Local Traits State (to support toggling placeholders or real traits locally)
const localTraits = ref<Trait[]>([])

const initializeTraits = () => {
  if (!props.hero) {
    localTraits.value = []
    return
  }
  
  const existing = props.hero.traits || []
  const defaults: Trait[] = [
    { name: '固有', rank: 'S', active: true },
    { name: '特性 2', rank: 'A', active: false }, // Default inactive per user request
    { name: '特性 3', rank: 'B', active: false },
    { name: '特性 4', rank: 'C', active: false }
  ]
  
  // Merge existing with defaults/placeholders
  localTraits.value = defaults.map((def, i) => {
    if (existing[i]) {
      // Use existing, ensure it has active property
      return { ...existing[i], active: existing[i].active ?? true }
    }
    return def
  })
}

watch(() => props.hero, (newHero) => {
  initializeTraits()
  if (newHero?.stats) {
    emit('update:stats', { ...newHero.stats })
  }
}, { immediate: true })

const toggleTrait = (index: number) => {
  // First trait usually locked, but user asked for "click to enable" logic for all? 
  // "第一個一定只會 enable" -> First one always enabled.
  if (index === 0) return 

  const trait = localTraits.value[index]
  if (trait) {
    trait.active = !trait.active
  }
}

const getTraitColor = (rank: string) => {
  switch (rank) {
    case 'S': return 'bg-yellow-50 border-yellow-300 text-yellow-700 font-bold'
    case 'A': return 'bg-purple-50 border-purple-300 text-purple-700 font-bold'
    case 'B': return 'bg-blue-50 border-blue-300 text-blue-700'
    default: return 'bg-gray-50 border-gray-200 text-gray-500' // C / White
  }
}

// Equip Traits Logic
const equipTraitDialogVisible = ref(false)
const currentEquipSlotIdx = ref<number | null>(null)

const openEquipTraitSelect = (idx: number) => {
  currentEquipSlotIdx.value = idx
  equipTraitDialogVisible.value = true
}

const selectEquipTrait = (trait: Trait | null) => {
  if (currentEquipSlotIdx.value === null) return
  
  // Clone current traits or create new array if empty
  const currentTraits = props.equipTraits ? [...props.equipTraits] : [null, null, null, null]
  currentTraits[currentEquipSlotIdx.value] = trait as any
  
  emit('update:equipTraits', currentTraits)
  equipTraitDialogVisible.value = false
}

const handleSkillDragStart = (event: DragEvent, slotIdx: number) => {
  const skill = slotIdx === 1 ? props.skill1 : props.skill2
  event.dataTransfer?.setData('application/skill-slot', JSON.stringify({ role: props.role, slotIdx }))
  event.dataTransfer!.effectAllowed = 'move'
  const ghost = new Image()
  ghost.src = TRANSPARENT_GIF
  event.dataTransfer?.setDragImage(ghost, 0, 0)
  draggingSlot.value = slotIdx
  emit('skill-drag-start', skill)
}

const handleDrop = (event: DragEvent, targetSlotIdx: number) => {
  event.preventDefault()
  if (event.dataTransfer?.types.includes('application/skill-slot')) {
    const src = JSON.parse(event.dataTransfer.getData('application/skill-slot'))
    emit('skill-slot-drop', src.role, src.slotIdx, targetSlotIdx)
    return
  }
  const skillData = event.dataTransfer?.getData('application/json')
  if (skillData) {
    try {
      const skill = JSON.parse(skillData)
      emit('skill-drop', targetSlotIdx, skill)
    } catch (e) {
      console.error('Invalid skill drop data')
    }
  }
}
</script>