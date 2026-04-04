<template>
  <div class="text-xs text-gray-500 truncate">
    <span v-for="(segment, index) in parsedText" :key="index">
      <span v-if="segment.type === 'text'">{{ segment.value }}</span>

      <span v-else-if="segment.type === 'status'" class="text-blue-600 font-bold">
        {{ segment.data?.name }}
      </span>

      <span v-else-if="segment.type === 'dmg'" class="text-red-600 font-bold">
        {{ segment.data?.name }}
      </span>

      <span v-else-if="segment.type === 'scale'" class="text-purple-600 font-bold">
        <span v-if="segment.data?.value">{{ segment.data.value }}</span>
        <span v-if="segment.data?.statInfo">受{{ segment.data.statInfo }}影響</span>
      </span>

      <span v-else-if="segment.type === 'stat'" class="text-emerald-600 font-bold">
        {{ segment.data?.name }}
      </span>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTemplateParser } from '../composables/useTemplateParser'

const props = defineProps({
  text: { type: String, default: '' },
  isMaxLevel: { type: Boolean, default: false }
})

const { parseText } = useTemplateParser()

const parsedText = computed(() => parseText(props.text, props.isMaxLevel))
</script>
