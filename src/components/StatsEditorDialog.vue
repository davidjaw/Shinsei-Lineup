<template>
  <el-dialog
    :model-value="modelValue"
    title="自由屬性加點"
    width="360px"
    append-to-body
    align-center
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
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
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button type="primary" @click="saveStats">確認修改</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Hero } from '../composables/useData'
import type { RoleData } from '../composables/useLineups'

type StatKey = 'lea' | 'val' | 'int' | 'pol' | 'cha' | 'spd'
type StatMap = RoleData['stats']

const STAT_KEYS: StatKey[] = ['lea', 'val', 'int', 'pol', 'cha', 'spd']

const props = defineProps<{
  modelValue: boolean
  hero: Hero | null | undefined
  stats: StatMap | null | undefined
  breakthrough?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:stats', stats: StatMap): void
}>()

// Base 50 free points, +10 per breakthrough star
const freePointsTotal = computed(() => 50 + (props.breakthrough ?? 0) * 10)

const heroBaseStats = computed<StatMap>(() => {
  const s = props.hero?.stats
  return {
    lea: s?.lea ?? 0, val: s?.val ?? 0, int: s?.int ?? 0,
    pol: s?.pol ?? 0, cha: s?.cha ?? 0, spd: s?.spd ?? 0,
  }
})

const statBonus = computed(() => {
  const base = heroBaseStats.value
  const result: Record<StatKey, number> = { lea: 0, val: 0, int: 0, pol: 0, cha: 0, spd: 0 }
  for (const k of STAT_KEYS) result[k] = (props.stats?.[k] ?? 0) - base[k]
  return result
})

const localBonus = ref<Record<StatKey, number>>({
  lea: 0, val: 0, int: 0, pol: 0, cha: 0, spd: 0,
})

const localFreeRemaining = computed(() => {
  let used = 0
  for (const k of STAT_KEYS) used += Math.max(0, localBonus.value[k] ?? 0)
  return freePointsTotal.value - used
})

watch(() => props.modelValue, (open) => {
  if (!open) return
  localBonus.value = { ...statBonus.value }
})

const adjustBonus = (key: string, delta: number) => {
  const k = key as StatKey
  const current = localBonus.value[k] ?? 0
  const newVal = current + delta
  if (newVal < 0) return
  if (delta > 0 && delta > localFreeRemaining.value) return
  localBonus.value[k] = newVal
}

const resetBonus = () => {
  for (const k of STAT_KEYS) localBonus.value[k] = 0
}

const saveStats = () => {
  const base = heroBaseStats.value
  const result: StatMap = { lea: 0, val: 0, int: 0, pol: 0, cha: 0, spd: 0 }
  for (const k of STAT_KEYS) result[k] = base[k] + (localBonus.value[k] ?? 0)
  emit('update:stats', result)
  emit('update:modelValue', false)
}

const statLabels: Record<StatKey, string> = {
  lea: '統',
  val: '武',
  int: '智',
  pol: '政',
  cha: '魅',
  spd: '速',
}
</script>
