<template>
  <div
    class="relative aspect-[3/4] rounded-md overflow-hidden border-2 transition-all group select-none"
    :class="[
      isRare
        ? 'border-yellow-400 ring-2 ring-yellow-300/70 shadow-md shadow-yellow-300/60'
        : 'border-gray-200 hover:border-orange-400',
      readonly
        ? ''
        : 'cursor-context-menu hover:scale-105 hover:shadow-md hover:z-10',
    ]"
    :title="readonly ? undefined : '右鍵或長按開啟選單'"
  >
    <img
      v-if="hero"
      :src="hero.portrait"
      class="w-full h-full object-cover object-top pointer-events-none"
      loading="lazy"
      @error="handleImageError"
    />
    <div
      v-else
      class="w-full h-full bg-gray-100 flex items-center justify-center text-[8px] text-gray-400 text-center px-0.5"
    >{{ draw.hero_jp }}</div>

    <!-- rare overlay: golden tint covers the whole card so a rare draw is
         unmistakable even at compact sizes (~12-16px wide horizontal strip). -->
    <div
      v-if="isRare"
      class="absolute inset-0 bg-gradient-to-b from-yellow-300/30 via-transparent to-yellow-400/25 pointer-events-none"
    ></div>

    <!-- rare star (top-right). Larger + solid backdrop so it survives the
         portrait darkness behind it. -->
    <div
      v-if="isRare"
      class="absolute top-0 right-0 px-1 py-0.5 bg-yellow-400 text-white text-xs font-bold leading-none rounded-bl shadow pointer-events-none"
    >★</div>

    <!-- date label and reverse-index sit just above the name overlay so they
         don't fight the rare-star or menu-button corners. -->
    <div class="absolute bottom-3.5 left-0 right-0 flex items-center justify-between px-0.5 pointer-events-none">
      <span
        v-if="dateLabel"
        class="bg-orange-500 text-white text-[8px] font-bold px-1 leading-tight rounded-sm"
      >{{ dateLabel }}</span>
      <span v-else></span>
      <span
        v-if="indexFromEnd != null"
        class="text-[8px] text-white/85 bg-black/55 px-1 rounded-sm tabular-nums leading-tight"
      >#{{ indexFromEnd }}</span>
    </div>

    <!-- name overlay -->
    <div class="absolute bottom-0 left-0 right-0 text-[9px] text-white bg-black/65 truncate text-center px-0.5 pointer-events-none">
      {{ hero?.name || draw.hero_jp }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { PropType } from 'vue'
import type { Hero } from '../composables/useData'
import type { GachaDraw } from '../composables/useGachaLog'

defineProps({
  draw: { type: Object as PropType<GachaDraw>, required: true },
  hero: { type: Object as PropType<Hero | undefined>, default: undefined },
  /** Whether this draw's hero is in the banner's rare set. Computed by the
   *  parent (GachaLogList) — rare-ness lives per banner, not per draw row. */
  isRare: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
  /** Optional date label shown only when this card opens a new date (flat mode). */
  dateLabel: { type: String as PropType<string | null>, default: null },
  /** Reverse-index from the latest draw (1 = newest). Shown subtly so the
   *  user can pinpoint a specific entry in a long sequential list. */
  indexFromEnd: { type: Number as PropType<number | null>, default: null },
})

// Inline SVG placeholder — singlefile build forbids external requests, and the
// previously-used placeholder.com domain returns 404 / blocks CSP intermittently.
const IMG_PLACEHOLDER =
  "data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 90 120'><rect width='90' height='120' fill='%23e5e7eb'/><text x='45' y='65' text-anchor='middle' font-family='sans-serif' font-size='10' fill='%239ca3af'>No%20Img</text></svg>"

const handleImageError = (e: Event) => {
  (e.target as HTMLImageElement).src = IMG_PLACEHOLDER
}
</script>
