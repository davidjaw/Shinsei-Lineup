<template>
  <Teleport to="body">
    <div v-if="skill"
      class="fixed z-[9999] pointer-events-none select-none"
      :style="{ left: pos.x + 16 + 'px', top: pos.y - 8 + 'px' }"
    >
      <div class="bg-white rounded-xl shadow-2xl border-2 border-indigo-400 p-3 w-64 max-h-72 overflow-hidden">
        <div class="flex items-center gap-2 mb-2">
          <SkillTypeMark :type="skill.type" size="drag" />
          <div class="min-w-0">
            <div class="font-bold text-sm text-gray-800 truncate">{{ skill.name }}</div>
            <div class="flex items-center gap-1 mt-0.5">
              <span class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{{ skill.type }}</span>
              <span v-if="skill.rarity === 'S'" class="text-xs font-bold text-yellow-600">S</span>
              <span v-if="skill.activation_rate" class="text-[10px] text-gray-400">{{ skill.activation_rate }}</span>
            </div>
          </div>
        </div>
        <SkillDescription
          :description="skill.description"
          :commander-description="skill.commander_description"
          :is-max-level="true"
          :vars="skill.vars"
        />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import SkillDescription from '../SkillDescription.vue'
import SkillTypeMark from '../SkillTypeMark.vue'
import type { Skill } from '../../composables/useData'

defineProps<{
  skill: Skill | null
  pos: { x: number; y: number }
}>()
</script>
