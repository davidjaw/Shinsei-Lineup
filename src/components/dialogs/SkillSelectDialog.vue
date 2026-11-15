<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    title="選擇戰法"
    width="90%"
    class="max-w-md skill-select-dialog"
    align-center
  >
    <div class="h-[60vh]">
      <SkillLibrary
        mode="select"
        :used-skills="usedSkills"
        :owned-skills="ownedSkills"
        :game-season="gameSeason"
        @select="(skill: Skill) => $emit('select', skill)"
      />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import SkillLibrary from '../SkillLibrary.vue'
import type { Skill } from '../../composables/useData'

defineProps<{
  modelValue: boolean
  usedSkills: Set<string>
  ownedSkills: string[]
  gameSeason: string
}>()
defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'select', skill: Skill): void
}>()
</script>
