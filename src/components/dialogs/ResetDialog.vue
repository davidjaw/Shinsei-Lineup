<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    title="重置選項"
    width="320px"
    align-center
  >
    <div class="flex flex-col gap-3">
      <el-button type="danger" plain size="large" @click="$emit('confirm', 'team')" class="w-full !m-0">
        <div class="flex flex-col items-center">
          <span class="font-bold">重置當前隊伍</span>
          <span class="text-xs opacity-80">僅清空目前顯示的隊伍</span>
        </div>
      </el-button>
      <el-button type="danger" plain size="large" @click="$emit('confirm', 'group')" class="w-full !m-0">
        <div class="flex flex-col items-center">
          <span class="font-bold">重置當前編組</span>
          <span class="text-xs opacity-80">清空目前編組內所有隊伍</span>
        </div>
      </el-button>
      <el-button type="warning" plain size="large" @click="$emit('confirm', 'inventory')" class="w-full !m-0">
        <div class="flex flex-col items-center">
          <span class="font-bold">清空庫存</span>
          <span class="text-xs opacity-80">移除本機標記的擁有武將與戰法</span>
        </div>
      </el-button>
      <el-button type="danger" size="large" @click="$emit('confirm', 'all')" class="w-full !m-0">
        <div class="flex flex-col items-center">
          <span class="font-bold">全部重置</span>
          <span class="text-xs opacity-80">清空自由／庫存兩邊的編組與庫存 (慎用)</span>
        </div>
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
export type ResetTarget = 'team' | 'group' | 'inventory' | 'all'

defineProps<{ modelValue: boolean }>()
defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', target: ResetTarget): void
}>()
</script>
