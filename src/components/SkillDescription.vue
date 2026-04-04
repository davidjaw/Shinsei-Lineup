<template>
  <div class="text-gray-700 leading-relaxed text-xs space-y-2">
    <!-- Main Description -->
    <div>
      <span v-for="(segment, index) in parsedDescription" :key="index">
        <span v-if="segment.type === 'text'">{{ segment.value }}</span>
        
        <el-tooltip 
          v-else-if="segment.type === 'status'"
          placement="top"
          :show-after="200"
        >
          <template #content>
            <div class="max-w-[200px]">
              <div class="font-bold mb-1">{{ segment.data.name }}</div>
              <div class="text-xs">{{ segment.data.description }}</div>
            </div>
          </template>
          <span class="text-blue-600 bg-blue-50 px-1 rounded cursor-help border-b border-blue-200 border-dashed hover:bg-blue-100 transition-colors">
            {{ segment.data.name }}
          </span>
        </el-tooltip>

        <span v-else-if="segment.type === 'dmg'" class="text-red-600 font-bold">
          {{ segment.data.name }}
        </span>

        <span v-else-if="segment.type === 'scale'" class="text-purple-600 font-bold">
          <span v-if="segment.data.value">{{ segment.data.value }}</span><span v-if="segment.data.statInfo">受{{ segment.data.statInfo }}影響</span>
        </span>

        <span v-else-if="segment.type === 'stat'" class="text-emerald-600 bg-emerald-50 px-1 rounded font-bold border border-emerald-200">
          {{ segment.data.name }}
        </span>
      </span>
    </div>

    <!-- Commander Description -->
    <div v-if="commanderDescription" class="bg-yellow-50 p-1.5 rounded border border-yellow-200 text-yellow-800">
      <div class="font-bold text-[10px] mb-0.5 flex items-center gap-1">
        <span class="bg-yellow-200 text-yellow-800 px-1 rounded">大將</span>
        效果
      </div>
      <div>
        <span v-for="(segment, index) in parsedCommander" :key="'cmd'+index">
          <span v-if="segment.type === 'text'">{{ segment.value }}</span>
          
          <el-tooltip 
            v-else-if="segment.type === 'status'"
            placement="top"
            :show-after="200"
          >
             <template #content>
              <div class="max-w-[200px]">
                <div class="font-bold mb-1">{{ segment.data.name }}</div>
                <div class="text-xs">{{ segment.data.description }}</div>
              </div>
            </template>
            <span class="text-blue-700 underline decoration-dashed cursor-help">
              {{ segment.data.name }}
            </span>
          </el-tooltip>

          <span v-else-if="segment.type === 'dmg'" class="text-red-700 font-bold">
            {{ segment.data.name }}
          </span>

          <span v-else-if="segment.type === 'scale'" class="text-purple-700 font-bold">
            <span v-if="segment.data.value">{{ segment.data.value }}</span><span v-if="segment.data.statInfo">受{{ segment.data.statInfo }}影響</span>
          </span>

          <span v-else-if="segment.type === 'stat'" class="text-emerald-700 bg-emerald-100 px-1 rounded font-bold border border-emerald-300">
            {{ segment.data.name }}
          </span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTemplateParser } from '../composables/useTemplateParser'

const props = defineProps({
  description: { type: String, default: '' },
  commanderDescription: { type: String, default: '' },
  isMaxLevel: { type: Boolean, default: false },
  vars: { type: Object, default: undefined }
})

const { parseText } = useTemplateParser()

const parsedDescription = computed(() => parseText(props.description, props.isMaxLevel, props.vars))
const parsedCommander = computed(() => parseText(props.commanderDescription, props.isMaxLevel, props.vars))
</script>