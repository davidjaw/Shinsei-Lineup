<template>
  <div class="relative flex justify-center items-center">
    <svg :width="size" :height="size" viewBox="0 0 100 100" class="overflow-visible">
      <!-- Background Grid (Hexagons) -->
      <polygon :points="getPolygonPoints(100)" fill="none" stroke="#e5e7eb" stroke-width="1" />
      <polygon :points="getPolygonPoints(66)" fill="none" stroke="#e5e7eb" stroke-width="1" />
      <polygon :points="getPolygonPoints(33)" fill="none" stroke="#e5e7eb" stroke-width="1" />

      <!-- Axis Lines -->
      <line v-for="(point, index) in axisPoints" :key="'axis'+index"
            x1="50" y1="50" :x2="point.x" :y2="point.y"
            stroke="#e5e7eb" stroke-width="1" />

      <!-- Base Stats Polygon (if baseStats provided) -->
      <polygon v-if="hasBonus" :points="baseDataPoints" fill="rgba(79, 70, 229, 0.1)" stroke="#a5b4fc" stroke-width="1" stroke-dasharray="3,2" />

      <!-- Final Stats Polygon -->
      <polygon :points="dataPoints" fill="rgba(79, 70, 229, 0.2)" stroke="#4f46e5" stroke-width="2" />

      <!-- Data Points (Dots) -->
      <circle v-for="(point, index) in currentPoints" :key="'dot'+index"
              :cx="point.x" :cy="point.y" r="2" fill="#4f46e5" />
    </svg>

    <!-- Labels -->
    <div class="absolute inset-0 pointer-events-none text-[8px] text-gray-500 font-bold">
      <span class="absolute top-0 left-1/2 -translate-x-1/2 -mt-1">統</span>
      <span class="absolute top-[25%] right-0 translate-x-1">武</span>
      <span class="absolute bottom-[25%] right-0 translate-x-1">智</span>
      <span class="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-2">政</span>
      <span class="absolute bottom-[25%] left-0 -translate-x-2">魅</span>
      <span class="absolute top-[25%] left-0 -translate-x-2">速</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps({
  stats: {
    type: Object, // { lea, val, int, pol, cha, spd } — final values (base + bonus)
    required: true
  },
  baseStats: {
    type: Object, // { lea, val, int, pol, cha, spd } — hero base (optional, for overlay)
    default: undefined
  },
  size: {
    type: Number,
    default: 80
  }
})

const statKeys = ['lea', 'val', 'int', 'pol', 'cha', 'spd']

const effectiveMax = computed(() => {
  let max = 0
  for (const key of statKeys) {
    const v = (props.stats as any)[key] || 0
    if (v > max) max = v
    if (props.baseStats) {
      const b = (props.baseStats as any)[key] || 0
      if (b > max) max = b
    }
  }
  // Round up to nearest 50 with some headroom
  return Math.max(150, Math.ceil(max / 50) * 50 + 25)
})

const hasBonus = computed(() => {
  if (!props.baseStats) return false
  return statKeys.some(k => (props.stats as any)[k] !== (props.baseStats as any)[k])
})

const getPoint = (value: number, index: number, maxRadius = 48) => {
  const angle = (Math.PI / 3) * index - Math.PI / 2
  const normalizedValue = Math.max(value, 0)
  const radius = (normalizedValue / effectiveMax.value) * maxRadius
  return {
    x: 50 + radius * Math.cos(angle),
    y: 50 + radius * Math.sin(angle)
  }
}

const getPolygonPoints = (percentage: number) => {
  return Array.from({ length: 6 }).map((_, i) => {
    const { x, y } = getPoint(effectiveMax.value * (percentage / 100), i)
    return `${x},${y}`
  }).join(' ')
}

const currentPoints = computed(() => {
  return statKeys.map((key, i) => getPoint((props.stats as any)[key] || 0, i))
})

const dataPoints = computed(() => {
  return currentPoints.value.map(p => `${p.x},${p.y}`).join(' ')
})

const baseDataPoints = computed(() => {
  if (!props.baseStats) return ''
  return statKeys.map((key, i) => {
    const { x, y } = getPoint((props.baseStats as any)[key] || 0, i)
    return `${x},${y}`
  }).join(' ')
})

const axisPoints = computed(() => {
  return Array.from({ length: 6 }).map((_, i) => getPoint(effectiveMax.value, i))
})
</script>
