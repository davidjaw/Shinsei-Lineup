// Gacha draw history state. Module-level reactive state shared across the
// dialog, picker, and spectator components — same pattern as useInventory.
//
// "Rare" is per (banner, hero name): the user picks which heroes count as
// rare for each banner, stored on the banner row's `rare_heroes` array. Every
// draw of one of those heroes renders as rare and resets pity. Toggling rare
// is a single PATCH to the banner — no per-draw state to keep in sync.

import { computed, ref, watch } from 'vue'
import {
  type GachaBanner,
  type GachaDraw,
  appendDraw as apiAppendDraw,
  createBanner as apiCreateBanner,
  deleteBanner as apiDeleteBanner,
  deleteDraw as apiDeleteDraw,
  listDraws as apiListDraws,
  listMyBanners,
  renameBanner as apiRenameBanner,
  updateBannerPool as apiUpdateBannerPool,
  updateBannerRareHeroes as apiUpdateBannerRareHeroes,
} from '../lib/gachaLog'
import { onSessionEvent } from '../lib/auth'
import type { Hero } from './useData'

const LAST_BANNER_KEY = 'nobunaga.gachaLog.lastBanner'
const DRAWS_TTL_MS = 5 * 60 * 1000

// ---------- module-level state ----------

const banners = ref<GachaBanner[]>([])
const currentBannerId = ref<string | null>(null)
// Map<bannerId, draws[]> cached in-memory. ref<Map> swap-on-mutation gives
// reliable reactivity across consumers.
const drawsByBanner = ref<Map<string, GachaDraw[]>>(new Map())
const drawsLoadedAt = new Map<string, number>()
const isLoading = ref(false)
// Per-banner generation: loadDraws and local mutations increment so a stale
// in-flight list cannot setDraws over a newer prepend, delete, or fetch.
const drawFetchGen = new Map<string, number>()
let loadsInFlight = 0

// ---------- pure helpers (also used by spectator view with its own draws) ----------

// Median gap (in draws) between consecutive rare entries. Caller passes the
// array of rare-position indices so this stays decoupled from where rare-ness
// is stored. Null when there are fewer than two rare entries.
export const computeMedianGap = (positions: number[]): number | null => {
  if (positions.length < 2) return null
  const gaps: number[] = []
  for (let i = 1; i < positions.length; i++) gaps.push(positions[i] - positions[i - 1])
  gaps.sort((a, b) => a - b)
  const mid = Math.floor(gaps.length / 2)
  return gaps.length % 2 === 0
    ? Math.round((gaps[mid - 1] + gaps[mid]) / 2)
    : gaps[mid]
}

// Top-N heroes by draw count, descending. Input is the per-hero count map
// (e.g. drawsPerHero) so callers can build it once and reuse.
export const computeTopHeroes = (
  perHero: Map<string, number>,
  limit = 10,
): { jp: string; count: number }[] => {
  const entries = Array.from(perHero.entries())
  entries.sort((a, b) => b[1] - a[1])
  return entries.slice(0, limit).map(([jp, count]) => ({ jp, count }))
}

// ---------- session lifecycle: reset on logout/expire ----------

const resetState = (): void => {
  banners.value = []
  currentBannerId.value = null
  drawsByBanner.value = new Map()
  drawsLoadedAt.clear()
  // Keep drawFetchGen so a stale in-flight list from the previous session
  // cannot pass the gen check after the next login restarts at 1.
}
onSessionEvent((e) => {
  if (e === 'signed-out' || e === 'expired') resetState()
})

// Persist last-used banner so the dialog reopens to the same context.
watch(currentBannerId, (id) => {
  if (id) localStorage.setItem(LAST_BANNER_KEY, id)
})

// ---------- helpers ----------

const setDraws = (bannerId: string, draws: GachaDraw[]): void => {
  const next = new Map(drawsByBanner.value)
  next.set(bannerId, draws)
  drawsByBanner.value = next
  drawsLoadedAt.set(bannerId, Date.now())
}

const isDrawCacheFresh = (bannerId: string): boolean => {
  const loaded = drawsLoadedAt.get(bannerId)
  return loaded != null && Date.now() - loaded < DRAWS_TTL_MS
}

const bumpDrawGen = (bannerId: string): number => {
  const next = (drawFetchGen.get(bannerId) ?? 0) + 1
  drawFetchGen.set(bannerId, next)
  return next
}

const beginLoad = (): void => {
  loadsInFlight++
  isLoading.value = true
}

const endLoad = (): void => {
  loadsInFlight = Math.max(0, loadsInFlight - 1)
  if (loadsInFlight === 0) isLoading.value = false
}

// ---------- derived ----------

const currentBanner = computed<GachaBanner | null>(() =>
  banners.value.find(b => b.id === currentBannerId.value) ?? null,
)

// Set view of the current banner's rare_heroes — O(1) hero membership checks
// for pity, filters, and per-draw rare highlight.
const currentRareSet = computed<Set<string>>(() =>
  new Set(currentBanner.value?.rare_heroes ?? []),
)

const currentDraws = computed<GachaDraw[]>(() => {
  if (!currentBannerId.value) return []
  return drawsByBanner.value.get(currentBannerId.value) ?? []
})

// Pity = consecutive non-rare draws since the most recent rare-hero draw (or
// total count if no rare draws exist). Scans the full array — early-exit on
// first rare hit makes this effectively O(pity), and matches what the
// spectator view computes from the snapshot blob.
const pityCount = computed<number>(() => {
  const draws = currentDraws.value
  const rare = currentRareSet.value
  let count = 0
  for (let i = 0; i < draws.length; i++) {
    if (rare.has(draws[i].hero_jp)) return count
    count++
  }
  return count
})

const totalDraws = computed<number>(() => currentDraws.value.length)

// Total draw count for rare heroes (every draw of a rare hero counts).
const markedCount = computed<number>(() => {
  const rare = currentRareSet.value
  if (rare.size === 0) return 0
  return currentDraws.value.reduce(
    (n, d) => n + (rare.has(d.hero_jp) ? 1 : 0), 0,
  )
})

// Per-hero appearance count (key = hero_jp). Used by Top 10 etc.
const drawsPerHero = computed<Map<string, number>>(() => {
  const m = new Map<string, number>()
  for (const d of currentDraws.value) m.set(d.hero_jp, (m.get(d.hero_jp) ?? 0) + 1)
  return m
})

// Per-rare-hero draw count: drawsPerHero filtered to keys in the rare set.
// Picker / Top 10 use `markedPerHero.has(jp)` as the rare flag.
const markedPerHero = computed<Map<string, number>>(() => {
  const rare = currentRareSet.value
  if (rare.size === 0) return new Map()
  const m = new Map<string, number>()
  for (const [jp, count] of drawsPerHero.value) {
    if (rare.has(jp)) m.set(jp, count)
  }
  return m
})

// ---------- actions ----------

const loadBanners = async (): Promise<void> => {
  beginLoad()
  try {
    banners.value = await listMyBanners()
    if (banners.value.length === 0) {
      currentBannerId.value = null
      return
    }
    // Restore last-used selection if still valid; otherwise first banner.
    const remembered = localStorage.getItem(LAST_BANNER_KEY)
    const matched = remembered && banners.value.find(b => b.id === remembered)
    currentBannerId.value = matched ? matched.id : banners.value[0].id
  } finally {
    endLoad()
  }
}

const loadDraws = async (bannerId: string, force = false): Promise<void> => {
  if (!force && isDrawCacheFresh(bannerId)) return
  const gen = bumpDrawGen(bannerId)
  beginLoad()
  try {
    const draws = await apiListDraws(bannerId)
    if (drawFetchGen.get(bannerId) !== gen) return
    setDraws(bannerId, draws)
  } finally {
    endLoad()
  }
}

const selectBanner = async (id: string): Promise<void> => {
  currentBannerId.value = id
  await loadDraws(id)
}

const createBanner = async (name: string): Promise<GachaBanner> => {
  const banner = await apiCreateBanner(name.trim())
  banners.value = [...banners.value, banner]
  setDraws(banner.id, [])
  currentBannerId.value = banner.id
  return banner
}

const renameBanner = async (id: string, name: string): Promise<void> => {
  const trimmed = name.trim()
  if (!trimmed) throw new Error('banner name cannot be empty')
  await apiRenameBanner(id, trimmed)
  banners.value = banners.value.map(b => (b.id === id ? { ...b, name: trimmed } : b))
}

const updateBannerPool = async (id: string, hero_pool: string[]): Promise<void> => {
  await apiUpdateBannerPool(id, hero_pool)
  banners.value = banners.value.map(b => (b.id === id ? { ...b, hero_pool } : b))
}

const deleteBanner = async (id: string): Promise<void> => {
  await apiDeleteBanner(id)
  banners.value = banners.value.filter(b => b.id !== id)
  const next = new Map(drawsByBanner.value)
  next.delete(id)
  drawsByBanner.value = next
  drawsLoadedAt.delete(id)
  drawFetchGen.delete(id)
  if (currentBannerId.value === id) {
    currentBannerId.value = banners.value[0]?.id ?? null
    if (currentBannerId.value) await loadDraws(currentBannerId.value)
  }
}

const logDraw = async (hero: Hero, rarity = 3): Promise<void> => {
  const bannerId = currentBannerId.value
  if (!bannerId) throw new Error('no banner selected')
  // Use JP name as canonical key, fall back to CHT for override-added heroes
  // that have name_jp = null (or absent). Same convention as profiles inv_h.
  const heroJp = hero.name_jp || hero.name
  const draw = await apiAppendDraw({ banner_id: bannerId, hero_jp: heroJp, rarity })
  // Invalidate in-flight list fetches so they cannot replace this prepend.
  bumpDrawGen(bannerId)
  // Insert at index 0 (newest first ordering matches server query).
  const next = new Map(drawsByBanner.value)
  next.set(bannerId, [draw, ...(next.get(bannerId) ?? [])])
  drawsByBanner.value = next
}

// Toggle rare-flag for a hero NAME within the current banner. The rare set
// lives on the banner row, so one PATCH is enough — every draw of this hero
// (past and future) immediately renders as rare. Per-banner scope only:
// each banner has its own rare set so the user retains full control over
// which heroes count as rare for which pull session.
const toggleHeroRare = async (heroJp: string): Promise<void> => {
  const banner = currentBanner.value
  if (!banner) return
  const current = banner.rare_heroes
  const next = current.includes(heroJp)
    ? current.filter(h => h !== heroJp)
    : [...current, heroJp]
  // Optimistic: swap rare_heroes on the local banner row first.
  const snapshot = current
  banners.value = banners.value.map(b =>
    b.id === banner.id ? { ...b, rare_heroes: next } : b,
  )
  try {
    await apiUpdateBannerRareHeroes(banner.id, next)
  } catch (e) {
    banners.value = banners.value.map(b =>
      b.id === banner.id ? { ...b, rare_heroes: snapshot } : b,
    )
    throw e
  }
}

const deleteDraw = async (drawId: number): Promise<void> => {
  const bannerId = currentBannerId.value
  if (!bannerId) return
  const list = drawsByBanner.value.get(bannerId)
  if (!list) return
  const idx = list.findIndex(d => d.id === drawId)
  if (idx < 0) return
  const removed = list[idx]
  const next = list.slice()
  next.splice(idx, 1)
  const cache = new Map(drawsByBanner.value)
  cache.set(bannerId, next)
  drawsByBanner.value = cache
  bumpDrawGen(bannerId)
  try {
    await apiDeleteDraw(drawId)
  } catch (e) {
    // Roll back insert at original position
    const rolled = next.slice()
    rolled.splice(idx, 0, removed)
    const rb = new Map(drawsByBanner.value)
    rb.set(bannerId, rolled)
    drawsByBanner.value = rb
    throw e
  }
}

export function useGachaLog() {
  return {
    // state
    banners,
    currentBannerId,
    isLoading,
    // derived
    currentBanner,
    currentRareSet,
    currentDraws,
    pityCount,
    totalDraws,
    markedCount,
    drawsPerHero,
    markedPerHero,
    // banner actions
    loadBanners,
    loadDraws,
    selectBanner,
    createBanner,
    renameBanner,
    updateBannerPool,
    deleteBanner,
    // draw actions
    logDraw,
    toggleHeroRare,
    deleteDraw,
  }
}

// Re-export types for convenient consumer imports.
export type { GachaBanner, GachaDraw } from '../lib/gachaLog'
