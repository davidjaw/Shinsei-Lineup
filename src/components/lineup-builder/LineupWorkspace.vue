<template>
  <div class="flex-1 flex flex-col md:flex-row h-full overflow-hidden">
    <!-- Left: 3-col Lineup Grid -->
    <div
      class="flex-none md:flex-1 overflow-y-auto p-0.5 md:p-[10px] bg-slate-50"
      @click.self="$emit('clear-skill-focus')"
    >
      <div
        class="grid grid-cols-3 md:grid-cols-3 lg:grid-cols-3 gap-0.5 md:gap-3 pb-0 md:pb-0 h-auto"
        :class="{ 'lineup-shake': lineupShakeActive }"
        @click.self="$emit('clear-skill-focus')"
        @animationend="$emit('update:lineupShakeActive', false)"
      >
        <div
          v-for="slot in SLOTS"
          :key="slot.role"
          class="w-full md:min-w-0 md:h-full"
        >
          <LineupSlot
            :title="slot.title"
            :role="slot.role"
            v-model:hero="currentLineup[slot.role].hero"
            v-model:skill1="currentLineup[slot.role].skill1"
            v-model:skill2="currentLineup[slot.role].skill2"
            v-model:stats="currentLineup[slot.role].stats"
            v-model:breakthrough="currentLineup[slot.role].breakthrough"
            v-model:bingxue="currentLineup[slot.role].bingxue"
            :focused-skill-slot="currentSelectingSkillRole === slot.role ? currentSelectingSkillSlot : null"
            :is-swap-source="swapModeRole === slot.role"
            :swap-mode-active="swapModeRole !== null"
            :is-drag-target="dragSourceRole !== null && dragSourceRole !== slot.role"
            :skill-dragging="isSkillDragging"
            :conflicting-skill-names="conflictingSkillNames"
            @open-hero-select="$emit('open-hero-select', slot.role)"
            @open-skill-select="(slotIdx: number) => $emit('open-skill-select', slot.role, slotIdx)"
            @skill-drop="(slotIdx: number, skill: Skill) => $emit('skill-drop', slot.role, slotIdx, skill)"
            @skill-drag-start="(skill: Skill) => $emit('skill-drag-start', skill)"
            @skill-drag-end="$emit('skill-drag-end')"
            @skill-slot-drop="(srcRole: Role, srcSlot: number, tgtSlot: number) => $emit('skill-slot-drop', slot.role, srcRole, srcSlot, tgtSlot)"
            @open-detail="$emit('open-detail', slot.role)"
            @swap-click="$emit('swap-click', slot.role)"
            @hero-drag-start="$emit('hero-drag-start', slot.role)"
            @hero-drag-end="$emit('hero-drag-end')"
            @hero-drop="$emit('hero-drop', slot.role)"
          />
        </div>
      </div>
    </div>

    <!-- Right: Library (Hero / Skill tabs) — below lineup on mobile -->
    <div class="flex-1 md:flex-none md:h-full w-full md:w-[45%] bg-white border-t md:border-t-0 md:border-l border-gray-200 flex flex-col shadow-xl z-40 min-h-0">
      <el-tabs
        :model-value="activeTab"
        @update:model-value="(v: string) => $emit('update:activeTab', v as 'heroes' | 'skills')"
        class="library-tabs flex-1 flex flex-col px-0 pt-0 md:px-4 md:pt-2"
        stretch
      >
        <el-tab-pane label="武將庫" name="heroes" class="h-full flex flex-col overflow-hidden">
          <HeroLibrary
            mode="select"
            :used-heroes="allUsedHeroNames"
            :owned-heroes="ownedHeroes"
            :filter-owned="showOwnedOnly"
            @select="(hero: Hero) => $emit('select-hero-from-library', hero)"
            @edit-inventory="$emit('edit-inventory')"
          />
        </el-tab-pane>
        <el-tab-pane label="戰法庫" name="skills" class="h-full flex flex-col overflow-hidden">
          <SkillLibrary
            mode="select"
            :used-skills="allUsedSkillNames"
            :owned-skills="ownedSkills"
            :filter-owned="showOwnedOnly"
            @select="(skill: Skill) => $emit('select-skill-from-library', skill)"
            @skill-drag-start="(skill: Skill) => $emit('skill-drag-start', skill)"
            @skill-drag-end="$emit('skill-drag-end')"
            @edit-inventory="$emit('edit-inventory')"
          />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import LineupSlot from '../LineupSlot.vue'
import HeroLibrary from '../HeroLibrary.vue'
import SkillLibrary from '../SkillLibrary.vue'
import type { Hero, Skill } from '../../composables/useData'
import type { Lineup } from '../../composables/useLineups'

export type Role = 'main' | 'vice1' | 'vice2'
export type LibraryTab = 'heroes' | 'skills'

const SLOTS: Array<{ role: Role; title: string }> = [
  { role: 'main', title: '大將' },
  { role: 'vice1', title: '副將' },
  { role: 'vice2', title: '副將' },
]

defineProps<{
  currentLineup: Lineup
  activeTab: LibraryTab
  ownedHeroes: string[]
  ownedSkills: string[]
  allUsedHeroNames: Set<string>
  allUsedSkillNames: Set<string>
  showOwnedOnly: boolean
  currentSelectingSkillRole: Role | null
  currentSelectingSkillSlot: number | null
  swapModeRole: Role | null
  dragSourceRole: Role | null
  isSkillDragging: boolean
  conflictingSkillNames: Set<string>
  lineupShakeActive: boolean
}>()

defineEmits<{
  (e: 'update:activeTab', v: LibraryTab): void
  (e: 'update:lineupShakeActive', v: boolean): void
  (e: 'clear-skill-focus'): void
  (e: 'open-hero-select', role: Role): void
  (e: 'open-skill-select', role: Role, slotIdx: number): void
  (e: 'skill-drop', role: Role, slotIdx: number, skill: Skill): void
  (e: 'skill-drag-start', skill: Skill): void
  (e: 'skill-drag-end'): void
  (e: 'skill-slot-drop', targetRole: Role, sourceRole: Role, sourceSlotIdx: number, targetSlotIdx: number): void
  (e: 'open-detail', role: Role): void
  (e: 'swap-click', role: Role): void
  (e: 'hero-drag-start', role: Role): void
  (e: 'hero-drag-end'): void
  (e: 'hero-drop', role: Role): void
  (e: 'select-hero-from-library', hero: Hero): void
  (e: 'select-skill-from-library', skill: Skill): void
  (e: 'edit-inventory'): void
}>()
</script>
