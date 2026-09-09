// Gacha draw history backend. Each user owns one or more banners; each banner
// has an append-only list of draws. The "rare" flag is per (banner, hero name)
// stored on the banner row — every draw of a hero in banner.rare_heroes is
// rendered as rare. Pity counter is derived client-side by scanning draws
// back to the most recent rare hero.
//
// Same PostgREST-via-fetch pattern as profiles.ts.

import { SUPABASE_URL, fetchWithTimeout, restHeaders } from './supabase'
import { requireAuth } from './auth'

export interface GachaBanner {
  id: string
  name: string
  is_active: boolean
  sort_order: number
  /** JP names of heroes that appear in this banner. Empty = pool not set
   *  yet (UI prompts user to define it before logging draws). */
  hero_pool: string[]
  /** JP names the user has flagged as "rare/紀念" within this banner. Source
   *  of truth for rare highlighting and pity reset — draws don't carry their
   *  own flag; rare-ness is looked up via this set. */
  rare_heroes: string[]
  created_at: string
  updated_at: string
}

export interface GachaDraw {
  id: number
  banner_id: string
  hero_jp: string
  rarity: number
  note: string | null
  drawn_at: string
}

// Subset of GachaDraw carried in shared snapshots. Rare-ness lives on the
// banner side of the blob, so draws only need identity + timing.
export interface SnapshotDraw {
  hero_jp: string
  rarity: number
  drawn_at: string
}

// v3 share blob payload. Schema versioned via the `v` field; bump on breaking
// shape changes so older clients can refuse to render rather than misinterpret.
export interface SpectatorBlob {
  v: 3
  kind: 'gacha_log'
  banner: {
    name: string
    /** Snapshot of banner.rare_heroes at share time. Spectators see exactly
     *  what the original user marked as rare. */
    rare_heroes: string[]
  }
  draws: SnapshotDraw[]
  meta: {
    snapshot_at: string
    display_name?: string | null
  }
}

const BANNER_COLS = 'id,name,is_active,sort_order,hero_pool,rare_heroes,created_at,updated_at'
const DRAW_COLS = 'id,banner_id,hero_jp,rarity,note,drawn_at'

// ---------- banners ----------

export const listMyBanners = async (): Promise<GachaBanner[]> => {
  const { userId, token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/gacha_banners?user_id=eq.${userId}` +
    `&select=${BANNER_COLS}&order=sort_order.asc,created_at.asc`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`list banners failed: ${res.status}`)
  return (await res.json()) as GachaBanner[]
}

export const createBanner = async (name: string): Promise<GachaBanner> => {
  const { userId, token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/gacha_banners?select=${BANNER_COLS}`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json', Prefer: 'return=representation' },
    body: JSON.stringify({ user_id: userId, name }),
  })
  if (!res.ok) throw new Error(`create banner failed: ${res.status} ${await res.text()}`)
  const rows = (await res.json()) as GachaBanner[]
  return rows[0]
}

interface BannerPatch {
  name?: string
  is_active?: boolean
  sort_order?: number
  hero_pool?: string[]
  rare_heroes?: string[]
}

const patchBanner = async (id: string, patch: BannerPatch): Promise<void> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/gacha_banners?id=eq.${encodeURIComponent(id)}`
  const res = await fetchWithTimeout(url, {
    method: 'PATCH',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json', Prefer: 'return=minimal' },
    body: JSON.stringify({ ...patch, updated_at: new Date().toISOString() }),
  })
  if (!res.ok) throw new Error(`update banner failed: ${res.status} ${await res.text()}`)
}

export const renameBanner = (id: string, name: string) => patchBanner(id, { name })

export const updateBannerPool = (id: string, hero_pool: string[]) =>
  patchBanner(id, { hero_pool })

export const updateBannerRareHeroes = (id: string, rare_heroes: string[]) =>
  patchBanner(id, { rare_heroes })

export const deleteBanner = async (id: string): Promise<void> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/gacha_banners?id=eq.${encodeURIComponent(id)}`
  const res = await fetchWithTimeout(url, {
    method: 'DELETE',
    headers: { ...restHeaders(token), Prefer: 'return=minimal' },
  })
  if (!res.ok) throw new Error(`delete banner failed: ${res.status} ${await res.text()}`)
}

// ---------- draws ----------

export interface ListDrawsOptions {
  /** Cap rows server-side. Default 1000 — covers most users; spectator views
   *  can pass a higher limit. PostgREST hard-caps at the table's policy limit. */
  limit?: number
}

export const listDraws = async (
  bannerId: string,
  opts: ListDrawsOptions = {},
): Promise<GachaDraw[]> => {
  const { userId, token } = await requireAuth()
  const limit = opts.limit ?? 1000
  const url = `${SUPABASE_URL}/rest/v1/gacha_draws?user_id=eq.${userId}` +
    `&banner_id=eq.${encodeURIComponent(bannerId)}` +
    `&select=${DRAW_COLS}&order=drawn_at.desc&limit=${limit}`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`list draws failed: ${res.status}`)
  return (await res.json()) as GachaDraw[]
}

export interface AppendDrawInput {
  banner_id: string
  hero_jp: string
  rarity?: number
  note?: string | null
}

export const appendDraw = async (input: AppendDrawInput): Promise<GachaDraw> => {
  const { userId, token } = await requireAuth()
  const row = {
    user_id: userId,
    banner_id: input.banner_id,
    hero_jp: input.hero_jp,
    rarity: input.rarity ?? 3,
    note: input.note ?? null,
  }
  const url = `${SUPABASE_URL}/rest/v1/gacha_draws?select=${DRAW_COLS}`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json', Prefer: 'return=representation' },
    body: JSON.stringify(row),
  })
  if (!res.ok) throw new Error(`append draw failed: ${res.status} ${await res.text()}`)
  const rows = (await res.json()) as GachaDraw[]
  return rows[0]
}

export const deleteDraw = async (id: number): Promise<void> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/gacha_draws?id=eq.${id}`
  const res = await fetchWithTimeout(url, {
    method: 'DELETE',
    headers: { ...restHeaders(token), Prefer: 'return=minimal' },
  })
  if (!res.ok) throw new Error(`delete draw failed: ${res.status} ${await res.text()}`)
}
