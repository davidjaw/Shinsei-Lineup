<template>
  <!-- Brand glyph. Easter egg: roughly once a minute the circled 猫 shatters
       into pixels that regroup into a pixel cat, idles for 15s, then
       morphs back. Five quick clicks play it now and restart the countdown.
       Skipped entirely under prefers-reduced-motion. -->
  <div
    ref="root"
    @click="onClick"
    class="relative w-8 h-8 rounded-full border text-brand flex items-center justify-center font-brand font-bold text-[15.4px] leading-none shrink-0"
    :class="phase === 'text' ? 'border-brand' : 'border-transparent'"
  >
    <span :class="phase !== 'text' && 'invisible'">猫</span>
    <svg
      v-if="phase !== 'text'"
      class="absolute -inset-px pointer-events-none"
      viewBox="0 0 16 16"
      width="32"
      height="32"
      shape-rendering="crispEdges"
      aria-hidden="true"
    >
      <g v-if="phase === 'morph'">
        <rect v-for="(_, i) in moves" :key="i" :ref="el => (rects[i] = el as SVGRectElement)" width="1" height="1" />
      </g>
      <g v-else>
        <path v-for="p in currentFrame" :key="p.fill" :fill="p.fill" :d="p.d" />
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { CAT_SPRITES, CAT_TICK_MS, planMorph, rasterizeGlyph, type CatSpriteId, type PixelMove } from '../../lib/pixelCat'

const IDLE_GAP_MS: [number, number] = [45_000, 75_000]
const CAT_HOLD_MS = 15_000
const SHATTER_MS = 120
const MOVE_MS = 650
const EASE = 'cubic-bezier(.45,-0.3,.25,1.35)'
const CLICKS_TO_TRIGGER = 5
const CLICK_GAP_MS = 800  // max pause between clicks of one streak

const root = ref<HTMLElement>()
const phase = ref<'text' | 'morph' | 'cat'>('text')
const spriteId = ref<CatSpriteId>('head')
const tick = ref(0)
const moves = shallowRef<PixelMove[]>([])
const rects: SVGRectElement[] = []

const currentFrame = computed(() => {
  const s = CAT_SPRITES[spriteId.value]
  return s.frames[s.timeline[tick.value % s.timeline.length] ?? 0] ?? []
})

const enabled = !matchMedia('(prefers-reduced-motion: reduce)').matches
let alive = true
let busy = false
let clicks = 0
let lastClick = 0
let timer: ReturnType<typeof setTimeout> | undefined
let hold: ReturnType<typeof setTimeout> | undefined
let ticker: ReturnType<typeof setInterval> | undefined
let anims: Animation[] = []
let glyphCells: [number, number][] | null = null

const sleep = (ms: number) => new Promise<void>(r => { hold = setTimeout(r, ms) })

function glyphSources(el: HTMLElement) {
  if (!glyphCells) {
    const cs = getComputedStyle(el)
    glyphCells = rasterizeGlyph('猫', `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`, parseFloat(cs.borderTopWidth) || 1, el.offsetWidth)
  }
  return glyphCells
}

async function fly(reverse: boolean, color: string) {
  phase.value = 'morph'
  await nextTick()
  const maxDelay = Math.max(...moves.value.map(m => m.delay))
  anims = moves.value.flatMap((m, i) => rects[i]?.animate([
    { transform: `translate(${m.from[0]}px,${m.from[1]}px) scale(.5)`, fill: color, opacity: 1 },
    { transform: `translate(${m.to[0]}px,${m.to[1]}px) scale(1)`, fill: m.color, opacity: m.fade ? 0 : 1 },
  ], {
    duration: MOVE_MS,
    delay: SHATTER_MS + (reverse ? maxDelay - m.delay : m.delay),
    easing: EASE,
    fill: 'both',
    direction: reverse ? 'reverse' : 'normal',
  }) ?? [])
  await Promise.all(anims.map(a => a.finished)).catch(() => {})
  anims = []
}

async function playOnce(el: HTMLElement) {
  const sources = glyphSources(el)
  if (!sources.length) return
  const color = getComputedStyle(el).color
  spriteId.value = Math.random() < 0.5 ? 'head' : 'body'
  moves.value = planMorph(sources, CAT_SPRITES[spriteId.value])

  await fly(false, color)
  if (!alive) return
  tick.value = 0
  phase.value = 'cat'
  ticker = setInterval(() => tick.value++, CAT_TICK_MS)
  await sleep(CAT_HOLD_MS)
  clearInterval(ticker)
  if (!alive) return
  await fly(true, color)
  if (!alive) return
  phase.value = 'text'
}

function scheduleNext() {
  clearTimeout(timer)
  const [lo, hi] = IDLE_GAP_MS
  timer = setTimeout(trigger, lo + Math.random() * (hi - lo))
}

async function trigger() {
  clearTimeout(timer)
  if (!alive) return
  if (busy || !root.value || document.hidden) return scheduleNext()
  busy = true
  await playOnce(root.value)
  busy = false
  if (alive) scheduleNext()
}

function onClick() {
  if (!enabled || busy) return
  const now = performance.now()
  clicks = now - lastClick > CLICK_GAP_MS ? 1 : clicks + 1
  lastClick = now
  if (clicks < CLICKS_TO_TRIGGER) return
  clicks = 0
  trigger()
}

onMounted(() => {
  if (enabled) scheduleNext()
})

onBeforeUnmount(() => {
  alive = false
  clearTimeout(timer)
  clearTimeout(hold)
  clearInterval(ticker)
  anims.forEach(a => a.cancel())
})
</script>
