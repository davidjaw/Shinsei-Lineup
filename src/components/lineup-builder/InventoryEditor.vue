<template>
  <div class="h-full bg-white flex flex-col">
    <div class="w-full md:container md:mx-auto h-full flex flex-col p-0 md:p-4">
      <el-tabs
        :model-value="activeTab"
        @update:model-value="(v: string) => $emit('update:activeTab', v)"
        class="inventory-tabs flex-1 flex flex-col"
        type="border-card"
      >
        <el-tab-pane label="武將庫存" name="heroes" class="h-full flex flex-col overflow-hidden">
          <HeroLibrary
            mode="manage"
            :game-season="gameSeason"
            :used-heroes="[]"
            :owned-heroes="ownedHeroes"
            @update:ownedHeroes="(val: string[]) => $emit('update:ownedHeroes', val)"
          />
        </el-tab-pane>
        <el-tab-pane label="戰法庫存" name="skills" class="h-full flex flex-col overflow-hidden">
          <SkillLibrary
            mode="manage"
            :game-season="gameSeason"
            :used-skills="new Set()"
            :owned-skills="ownedSkills"
            @update:ownedSkills="(val: string[]) => $emit('update:ownedSkills', val)"
          />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import HeroLibrary from '../HeroLibrary.vue'
import SkillLibrary from '../SkillLibrary.vue'

// `gameSeason` lists only what that season offers; what is owned outside it stays owned (全選 acts on the list shown).
defineProps<{
  activeTab: string
  ownedHeroes: string[]
  ownedSkills: string[]
  gameSeason: string
}>()
defineEmits<{
  (e: 'update:activeTab', v: string): void
  (e: 'update:ownedHeroes', v: string[]): void
  (e: 'update:ownedSkills', v: string[]): void
}>()
</script>
