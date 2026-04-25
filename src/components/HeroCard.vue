<template>
  <div 
    class="flex flex-col bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden cursor-pointer hover:shadow-md transition-shadow relative"
    :class="variant === 'lineup' ? 'h-auto w-auto' : 'h-full w-full'"
  >
    <!-- Rarity Indicator (Top Right) -->
    <div v-if="!compact" class="absolute top-0 right-0 z-10">
      <div v-if="hero.rarity == 5" class="bg-yellow-500 text-white text-[9px] md:text-xs px-1 md:px-2 py-0.5 rounded-bl-lg font-bold">S</div>
      <div v-else-if="hero.rarity == 4" class="bg-purple-500 text-white text-[9px] md:text-xs px-1 md:px-2 py-0.5 rounded-bl-lg font-bold">A</div>
      <div v-else class="bg-blue-500 text-white text-[9px] md:text-xs px-1 md:px-2 py-0.5 rounded-bl-lg font-bold">B</div>
    </div>

    <!-- Cost (Top Left) -->
    <div v-if="!compact" class="absolute top-0 left-0 z-10 bg-black/60 text-white text-[9px] md:text-xs px-1 md:px-1.5 py-0.5 rounded-br-lg">
      {{ hero.cost }}C
    </div>

    <!-- Image Container -->
    <div 
      class="relative bg-gray-100 flex justify-center overflow-hidden"
      :class="variant === 'lineup' ? 'h-[350px] aspect-[3/4]' : 'w-full aspect-[3/4]'"
    >
      <img 
        :src="hero.portrait" 
        class="w-full h-full object-cover object-top" 
        loading="lazy"
        @error="handleImageError"
      />
      <!-- Camp overlay -->
      <div v-if="!compact" class="absolute bottom-0 left-0 w-full bg-gradient-to-t from-black/90 via-black/60 to-transparent pt-4 md:pt-6 pb-0.5 md:pb-1 px-1 md:px-1.5">
        <div class="text-white text-[9px] md:text-xs font-bold flex items-center gap-1">
          <span>{{ hero.faction }}</span>
          <span v-if="hero.clan" class="opacity-80 font-normal">· {{ hero.clan }}</span>
        </div>
      </div>
    </div>

    <!-- Info -->
    <div v-if="!hideName" class="flex flex-col gap-1" :class="compact ? 'p-1' : 'p-0.5 md:p-2'">
      <div
        class="font-bold text-gray-800 truncate text-center"
        :class="compact ? 'text-[10px]' : 'text-[10px] md:text-sm'"
      >
        {{ hero.name }}
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { PropType } from 'vue'
import { Hero } from '../composables/useData'

const props = defineProps({
  hero: {
    type: Object as PropType<Hero>,
    required: true
  },
  variant: {
    type: String as PropType<'lineup' | 'library'>,
    default: 'library' // Default to library to be safe for lists
  },
  compact: {
    type: Boolean,
    default: false
  },
  hideName: {
    type: Boolean,
    default: false
  }
})

const handleImageError = (e: Event) => {
  (e.target as HTMLImageElement).src = 'https://via.placeholder.com/150?text=No+Img'
}
</script>
