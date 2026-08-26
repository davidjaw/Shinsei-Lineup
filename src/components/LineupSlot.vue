<template>
  <div class="bg-white rounded-md shadow-sm border border-divider flex flex-col h-full relative overflow-hidden">
    <!-- Shared SVG defs for breakthrough star gradient -->
    <svg width="0" height="0" class="absolute pointer-events-none" aria-hidden="true">
      <defs>
        <linearGradient id="breakStarGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#fff7c2" />
          <stop offset="35%" stop-color="#fbbf24" />
          <stop offset="70%" stop-color="#f97316" />
          <stop offset="100%" stop-color="#b91c1c" />
        </linearGradient>
        <radialGradient id="breakStarGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#fde68a" stop-opacity="0.9" />
          <stop offset="100%" stop-color="#dc2626" stop-opacity="0" />
        </radialGradient>
      </defs>
    </svg>

    <!-- Header strip: row 1 = role + actions; row 2 = hero name (left) + stars (right).
         Cost & rarity are surfaced by the HeroCard portrait overlays — no chip here. -->
    <div class="bg-white border-b border-divider px-1.5 md:px-2.5 pt-1 md:pt-1.5 pb-1 md:pb-1.5">
      <!-- Top row: role label + action buttons (mobile swap/detail/remove) -->
      <div class="flex items-center justify-between gap-1">
        <span class="text-[9px] md:text-[11px] font-bold text-ink-mute tracking-wider flex-shrink-0">{{ title }}</span>
        <div class="flex items-center flex-shrink-0">
          <!-- Mobile swap -->
          <el-button
            v-if="hero"
            link
            size="small"
            class="md:hidden !p-0 !h-auto mr-0.5"
            :class="isSwapSource ? 'text-focus' : 'text-ink-mute'"
            @click.stop="$emit('swap-click')"
          >
            <el-icon><Sort /></el-icon>
          </el-button>
          <!-- Mobile detail -->
          <el-button v-if="hero" link size="small" class="md:hidden !p-0 !h-auto mr-0.5" @click.stop="$emit('open-detail')">
            <el-icon class="text-ink-mute"><InfoFilled /></el-icon>
          </el-button>
          <!-- Remove -->
          <el-button v-if="hero" type="danger" link size="small" class="!p-0 !h-auto" @click="removeHero">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>
      <!-- Bottom row: hero name (flex-1, truncates) + breakthrough stars (right-aligned) -->
      <div v-if="hero" class="flex items-center gap-1 mt-0.5 md:mt-1">
        <div
          class="flex-1 min-w-0 font-bold text-ink truncate text-[11px] md:text-sm"
          :title="hero.name"
        >
          {{ hero.name }}
        </div>
        <!-- Desktop: inline stars with hover-fill preview -->
        <div
          class="hidden md:flex items-center gap-0 flex-shrink-0"
          @mouseleave="hoverStar = 0"
        >
          <button
            v-for="n in maxBreakthrough"
            :key="n"
            type="button"
            class="breakthrough-star"
            :class="{ 'is-filled': n <= displayStarCount }"
            :title="breakthrough === n ? '再次點擊重置' : `設定為 ${n} 星突破`"
            @mouseenter="hoverStar = n"
            @click.stop="setBreakthrough(n)"
          >
            <svg viewBox="0 0 24 24" width="13" height="13" class="break-star-svg">
              <path d="M12 2.5 L14.85 9.1 L22 9.77 L16.5 14.64 L18.18 21.52 L12 17.77 L5.82 21.52 L7.5 14.64 L2 9.77 L9.15 9.1 Z" />
            </svg>
          </button>
        </div>
        <!-- Mobile: single star + ×N badge popover -->
        <el-popover
          v-if="!isDesktop"
          ref="popoverRef"
          placement="bottom-end"
          trigger="click"
          :width="220"
          popper-class="breakthrough-popover"
          @hide="hoverStar = 0"
        >
          <template #reference>
            <button
              type="button"
              class="breakthrough-star flex items-center gap-0.5 flex-shrink-0"
              :class="{ 'is-filled': breakthrough > 0 }"
            >
              <svg viewBox="0 0 24 24" width="13" height="13" class="break-star-svg">
                <path d="M12 2.5 L14.85 9.1 L22 9.77 L16.5 14.64 L18.18 21.52 L12 17.77 L5.82 21.52 L7.5 14.64 L2 9.77 L9.15 9.1 Z" />
              </svg>
              <span v-if="breakthrough > 1" class="text-[8px] font-bold leading-none text-red-600">×{{ breakthrough }}</span>
            </button>
          </template>
          <div class="text-center text-[11px] font-bold text-gray-600 mb-1">突破次數</div>
          <div
            class="flex items-center justify-center gap-1 py-1"
            @mouseleave="hoverStar = 0"
          >
            <button
              v-for="n in maxBreakthrough"
              :key="n"
              type="button"
              class="breakthrough-star"
              :class="{ 'is-filled': n <= displayStarCount }"
              @mouseenter="hoverStar = n"
              @click.stop="onMobilePickStar(n)"
            >
              <svg viewBox="0 0 24 24" width="26" height="26" class="break-star-svg">
                <path d="M12 2.5 L14.85 9.1 L22 9.77 L16.5 14.64 L18.18 21.52 L12 17.77 L5.82 21.52 L7.5 14.64 L2 9.77 L9.15 9.1 Z" />
              </svg>
            </button>
          </div>
          <div class="text-center text-[10px] text-gray-400 mt-1">
            點擊當前星數可重置
          </div>
        </el-popover>
      </div>
    </div>

    <!-- Body -->
    <div class="p-1 md:p-2 flex flex-col gap-1 md:gap-2 flex-1 min-h-0">
      <!-- Hero portrait -->
      <div
        class="rounded border-2 border-dashed flex items-center justify-center cursor-pointer transition-all relative overflow-hidden group w-full aspect-[3/4] flex-shrink-0"
        :class="isDragTarget
          ? 'border-focus bg-highlight scale-[1.02] shadow-md'
          : isSwapSource
            ? 'border-focus ring-2 ring-focus'
            : swapModeActive
              ? 'border-focus/40 ring-2 ring-highlight'
              : 'border-divider hover:border-focus'"
        :draggable="!!hero"
        @click="$emit('open-hero-select')"
        @dragstart="handleHeroDragStart"
        @dragend="$emit('hero-drag-end')"
        @dragover.prevent
        @drop.prevent="handleHeroDropEvent"
      >
        <div v-if="isDragTarget" class="absolute inset-0 flex flex-col items-center justify-center z-10 bg-highlight/70 pointer-events-none">
          <el-icon class="text-focus text-xl md:text-3xl"><Sort /></el-icon>
          <span class="text-focus text-[8px] md:text-xs mt-1 font-medium">放置交換</span>
        </div>
        <HeroCard v-if="hero" :hero="hero" hide-name class="w-full h-full border-none shadow-none pointer-events-none" />
        <div v-else class="text-ink-mute flex flex-col items-center py-2 md:py-10">
          <el-icon :size="16" class="md:text-3xl"><Plus /></el-icon>
          <span class="text-[9px] md:text-xs mt-0.5">選擇</span>
        </div>
      </div>

      <!-- Stats row (only when hero) — click opens stats editor.
           freePointsRemaining shown in tooltip via title; bonus colour cues
           which stats already received free points.
           Hidden on mobile — the MobileSlotDetailDrawer surfaces these instead. -->
      <div
        v-if="hero"
        class="hidden md:block rounded border border-divider bg-white cursor-pointer hover:border-focus transition-colors px-1 py-1 md:px-1.5 md:py-1"
        :title="`點擊調整自由加點 · 剩餘 ${freePointsRemaining} 點`"
        @click.stop="openStatsEditor"
      >
        <div class="grid grid-cols-6 gap-0.5">
          <div v-for="key in STAT_KEYS" :key="key" class="flex flex-col items-center leading-none">
            <span class="text-[8px] md:text-[9px] text-ink-mute mb-0.5">{{ statLabels[key] }}</span>
            <span class="text-[10px] md:text-xs font-bold text-ink">{{ heroBaseStats[key] + (statBonus[key] || 0) }}</span>
            <span v-if="statBonus[key] > 0" class="text-[7px] md:text-[8px] text-emerald-600 mt-0.5">+{{ statBonus[key] }}</span>
            <span v-else-if="statBonus[key] < 0" class="text-[7px] md:text-[8px] text-red-500 mt-0.5">{{ statBonus[key] }}</span>
            <span v-else class="text-[7px] md:text-[8px] text-transparent mt-0.5 select-none">·</span>
          </div>
        </div>
      </div>

      <!-- Traits 2x2 full-width (only when hero) -->
      <div v-if="hero" class="grid grid-cols-2 gap-1 md:gap-1.5">
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
                {{ traitUnlockLabel(idx) }}{{ trait.active ? '' : ' · 尚未啟用' }}
              </div>
            </div>
          </template>
          <div
            class="rounded px-1.5 py-1 md:px-2 md:py-1 text-[10px] md:text-xs text-center border cursor-pointer transition-all select-none truncate"
            :class="[
              getTraitColor(trait.rank),
              { 'opacity-50 saturate-50': !trait.active }
            ]"
          >
            {{ trait.name }}
          </div>
        </el-tooltip>
      </div>

      <!-- Bingxue (only when hero) -->
      <div v-if="hero">
        <BingxueSection
          :hero="hero"
          :model-value="bingxue || { direction: null, major: null, minors: [] }"
          @update:model-value="(v) => $emit('update:bingxue', v)"
        />
      </div>

      <!-- Skills area -->
      <div class="flex flex-col gap-1 md:gap-1.5 flex-1 min-h-0">
        <!-- Unique Skill (Auto-filled) -->
        <el-popover
          placement="bottom"
          :offset="12"
          :title="hero?.unique_skill || '---'"
          :width="240"
          trigger="hover"
          :disabled="!hero?.unique_skill"
        >
          <template #reference>
            <div class="flex items-center gap-1 md:gap-2 p-0.5 md:p-2 bg-highlight rounded border border-divider opacity-90">
              <SkillTypeMark :type="uniqueSkillData?.type" size="slot" own />
              <div class="flex-1 min-w-0">
                <div class="text-[9px] md:text-sm text-ink-soft truncate mb-0.5">{{ hero?.unique_skill || '---' }}</div>
                <BriefDescription v-if="uniqueSkillData?.brief_description" :text="uniqueSkillData.brief_description" :vars="uniqueSkillData.vars" class="hidden md:block text-[7px] md:text-[11px] italic text-ink-soft" />
              </div>
            </div>
          </template>
          <div v-if="uniqueSkillData" class="text-xs space-y-2">
            <div class="flex justify-between items-start">
              <div class="font-bold text-focus flex flex-col">
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
          placement="bottom"
          :offset="12"
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
                isConflictSkill(skill1)
                  ? 'ring-1 md:ring-2 ring-red-500 bg-red-50 border-red-500'
                  : focusedSkillSlot === 1
                    ? 'ring-1 md:ring-2 ring-focus bg-highlight border-focus'
                    : dragOverSlot === 1
                      ? 'border-focus bg-highlight ring-2 ring-focus scale-[1.02]'
                      : skillDragging
                        ? 'border-dashed border-focus/50 bg-highlight/50'
                        : 'border-divider hover:border-focus'
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
              <SkillTypeMark v-if="skill1" :type="skill1.type" size="slot" />
              <div v-else class="w-5 h-5 md:w-8 md:h-8 bg-surface-muted rounded flex items-center justify-center text-ink-mute flex-shrink-0">
                <el-icon class="text-[10px] md:text-base"><Plus /></el-icon>
              </div>

              <div class="flex-1 min-w-0">
                <div v-if="skill1" class="text-[9px] md:text-sm font-bold text-ink truncate mb-0.5">{{ skill1.name }}</div>
                <div v-else class="text-[9px] md:text-sm text-ink-mute mb-0.5">習得</div>
                <BriefDescription v-if="skill1?.brief_description" :text="skill1.brief_description" :vars="skill1.vars" class="hidden md:block text-[7px] md:text-[11px] italic text-ink-soft" />
              </div>
              <el-button v-if="skill1" link type="danger" size="small" class="!p-0 !h-auto" @click.stop="$emit('update:skill1', null)">
                <el-icon :size="10"><Close /></el-icon>
              </el-button>
            </div>
          </template>
          <div v-if="skill1" class="text-xs space-y-2">
            <div class="flex justify-between items-start">
              <div class="font-bold text-focus flex flex-col">
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
          placement="bottom"
          :offset="12"
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
                isConflictSkill(skill2)
                  ? 'ring-1 md:ring-2 ring-red-500 bg-red-50 border-red-500'
                  : focusedSkillSlot === 2
                    ? 'ring-1 md:ring-2 ring-focus bg-highlight border-focus'
                    : dragOverSlot === 2
                      ? 'border-focus bg-highlight ring-2 ring-focus scale-[1.02]'
                      : skillDragging
                        ? 'border-dashed border-focus/50 bg-highlight/50'
                        : 'border-divider hover:border-focus'
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
              <SkillTypeMark v-if="skill2" :type="skill2.type" size="slot" />
              <div v-else class="w-5 h-5 md:w-8 md:h-8 bg-surface-muted rounded flex items-center justify-center text-ink-mute flex-shrink-0">
                <el-icon class="text-[10px] md:text-base"><Plus /></el-icon>
              </div>

              <div class="flex-1 min-w-0">
                <div v-if="skill2" class="text-[9px] md:text-sm font-bold text-ink truncate mb-0.5">{{ skill2.name }}</div>
                <div v-else class="text-[9px] md:text-sm text-ink-mute mb-0.5">習得</div>
                <BriefDescription v-if="skill2?.brief_description" :text="skill2.brief_description" :vars="skill2.vars" class="hidden md:block text-[7px] md:text-[11px] italic text-ink-soft" />
              </div>
              <el-button v-if="skill2" link type="danger" size="small" class="!p-0 !h-auto" @click.stop="$emit('update:skill2', null)">
                <el-icon :size="10"><Close /></el-icon>
              </el-button>
            </div>
          </template>
          <div v-if="skill2" class="text-xs space-y-2">
            <div class="flex justify-between items-start">
              <div class="font-bold text-focus flex flex-col">
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
    </div>

    <!-- Stats Editor Dialog -->
    <el-dialog v-model="statsDialogVisible" title="自由屬性加點" width="360px" append-to-body align-center>
      <div class="flex flex-col gap-3">
        <div class="text-xs text-gray-500 flex justify-between">
          <span>剩餘可分配點數</span>
          <span class="font-bold" :class="localFreeRemaining < 0 ? 'text-red-500' : 'text-focus'">{{ localFreeRemaining }} / {{ freePointsTotal }}</span>
        </div>
        <div class="space-y-2">
          <div v-for="(label, key) in statLabels" :key="key" class="flex items-center gap-1.5">
            <div class="w-8 text-xs font-bold text-gray-600">{{ label }}</div>
            <div class="text-xs text-gray-400 w-8 text-right">{{ heroBaseStats[key] }}</div>
            <button class="px-1.5 py-0.5 text-xs rounded border hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              :disabled="localBonus[key] <= 0"
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
  </div>
</template>

<script setup lang="ts">
import { PropType, ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { Plus, Close, InfoFilled, Sort } from '@element-plus/icons-vue'
import HeroCard from './HeroCard.vue'
import SkillDescription from './SkillDescription.vue'
import BriefDescription from './BriefDescription.vue'
import SkillTypeMark from './SkillTypeMark.vue'
import BingxueSection from './BingxueSection.vue'
import type { BingxueActive } from '../composables/useLineups'
import { Hero, Skill, Trait, useData } from '../composables/useData'
import { useTemplateParser } from '../composables/useTemplateParser'

import { TRANSPARENT_GIF, formatRate as _formatRate, getTraitColor } from '../constants/gameData'
import { TRAIT_UNLOCK } from '../constants/traits'

const props = defineProps({
  title: String,
  role: String,
  hero: Object as PropType<Hero | null>,
  skill1: Object as PropType<Skill | null>,
  skill2: Object as PropType<Skill | null>,
  stats: Object as PropType<any>,
  breakthrough: { type: Number, default: 0 },
  bingxue: { type: Object as PropType<BingxueActive>, default: () => ({ direction: null, major: null, minors: [] }) },
  focusedSkillSlot: Number as PropType<number | null>,
  isSwapSource: { type: Boolean, default: false },
  swapModeActive: { type: Boolean, default: false },
  isDragTarget: { type: Boolean, default: false },
  skillDragging: { type: Boolean, default: false },
  conflictingSkillNames: { type: Object as PropType<Set<string>>, default: () => new Set<string>() },
})

const isConflictSkill = (skill: Skill | null | undefined) =>
  !!skill && props.conflictingSkillNames.has(skill.name)

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
  'update:breakthrough',
  'update:bingxue',
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
  emit('update:breakthrough', 0)
  emit('update:bingxue', { direction: null, major: null, minors: [] })
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
// Base 50 free points, +10 per breakthrough star
const freePointsTotal = computed(() => 50 + (props.breakthrough ?? 0) * 10)
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
  return freePointsTotal.value - used
})

// Local editing state
const localBonus = ref<Record<string, number>>({})

const localFreeRemaining = computed(() => {
  let used = 0
  for (const k of STAT_KEYS) used += Math.max(0, localBonus.value[k] ?? 0)
  return freePointsTotal.value - used
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
  if (newVal < 0) return
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
  lea: '統',
  val: '武',
  int: '智',
  pol: '政',
  cha: '魅',
  spd: '速'
}

const localTraits = computed<Trait[]>(() => {
  if (!props.hero) return []
  const existing = props.hero.traits || []
  const defaults: Trait[] = [
    { name: '固有', rank: 'S', active: true },
    { name: '特性 2', rank: 'A', active: false },
    { name: '特性 3', rank: 'B', active: false },
    { name: '特性 4', rank: 'C', active: false },
  ]
  return defaults.map((def, i) => {
    const base = existing[i] ? { ...existing[i] } : def
    return { ...base, active: props.breakthrough >= TRAIT_UNLOCK[i] }
  })
})

const traitUnlockLabel = (idx: number) => {
  const req = TRAIT_UNLOCK[idx]
  if (req === 0) return '固有特性 (永久生效)'
  return `需要 ${req} 星突破解鎖`
}

// Max breakthrough is capped by rarity: S(5★)→5, A(4★)→4, B(3★)→3.
const maxBreakthrough = computed(() => {
  const r = Number(props.hero?.rarity ?? 0)
  if (r >= 5) return 5
  if (r === 4) return 4
  return 3
})

// Clamp a breakthrough that exceeds the hero's rarity cap (e.g. restored data,
// or a hero whose rarity is lower than a previously-stored value). This only
// caps; it NEVER resets to base. Resetting stats/breakthrough on a genuine hero
// assignment is the parent's job (LineupBuilder.selectHeroFromLibrary) — doing
// it here on any props.hero change would also fire on team switch / restore,
// where props.hero changes merely because the slot now shows a different team,
// and would wipe the user's saved 突破/屬性.
watch(() => props.hero, () => {
  if (props.hero && props.breakthrough > maxBreakthrough.value) {
    emit('update:breakthrough', maxBreakthrough.value)
  }
}, { immediate: true })

// Breakthrough stars: click star N → set to N; click the current value → reset to 0.
const setBreakthrough = (n: number) => {
  if (n > maxBreakthrough.value) return
  const next = props.breakthrough === n ? 0 : n
  emit('update:breakthrough', next)
}

// Track viewport so the mobile-only popover is fully removed from DOM on desktop
// (el-popover's reference wrapper ignores md:hidden, leaving a ghost star visible).
const isDesktop = ref(false)
let mq: MediaQueryList | null = null
const updateIsDesktop = (e: MediaQueryListEvent | MediaQueryList) => {
  isDesktop.value = e.matches
}
onMounted(() => {
  mq = window.matchMedia('(min-width: 768px)')
  isDesktop.value = mq.matches
  mq.addEventListener('change', updateIsDesktop)
})
onBeforeUnmount(() => {
  mq?.removeEventListener('change', updateIsDesktop)
})

// Hover-fill preview: when hovering star n, show n stars lit regardless of breakthrough.
const hoverStar = ref(0)

// Mobile popover ref so we can dismiss after a pick.
const popoverRef = ref<any>(null)
const onMobilePickStar = (n: number) => {
  const wasReset = props.breakthrough === n
  setBreakthrough(n)
  if (!wasReset) popoverRef.value?.hide?.()
}
const displayStarCount = computed(() =>
  hoverStar.value > 0 ? hoverStar.value : props.breakthrough
)

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

<style scoped>
.breakthrough-star {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 1px;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.2s ease;
}
.breakthrough-star .break-star-svg {
  fill: #e5e7eb;
  stroke: #9ca3af;
  stroke-width: 1.2;
  stroke-linejoin: round;
  transition: fill 0.25s ease, stroke 0.2s ease, transform 0.2s ease;
}
.breakthrough-star:hover {
  transform: scale(1.18) rotate(-4deg);
}
.breakthrough-star:hover .break-star-svg {
  fill: #fde68a;
  stroke: #f59e0b;
}
.breakthrough-star.is-filled .break-star-svg {
  fill: url(#breakStarGrad);
  stroke: #7f1d1d;
  stroke-width: 1;
}
.breakthrough-star.is-filled {
  animation: break-star-pop 0.35s ease;
}
.breakthrough-star.is-filled:hover {
  transform: scale(1.22) rotate(-6deg);
}
@keyframes break-star-pop {
  0%   { transform: scale(0.6) rotate(-20deg); }
  60%  { transform: scale(1.25) rotate(6deg); }
  100% { transform: scale(1) rotate(0); }
}
</style>
