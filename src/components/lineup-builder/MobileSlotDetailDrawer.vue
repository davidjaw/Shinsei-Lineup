<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    direction="btt"
    size="60%"
    :with-header="false"
    class="rounded-t-xl overflow-hidden"
  >
    <MobileSlotDetail
      v-if="role && roleData"
      :role-name="role === 'main' ? '大將' : '副將'"
      :hero="roleData.hero"
      :stats="roleData.stats"
      :breakthrough="roleData.breakthrough"
      @update:stats="(s) => $emit('update:stats', s)"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import MobileSlotDetail from '../MobileSlotDetail.vue'
import type { RoleData } from '../../composables/useLineups'

defineProps<{
  modelValue: boolean
  role: 'main' | 'vice1' | 'vice2' | null
  roleData: RoleData | null
}>()
defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:stats', stats: RoleData['stats']): void
}>()
</script>
