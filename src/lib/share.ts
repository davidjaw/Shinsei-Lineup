// Short-URL share backend. Stores the same payload that the legacy hash-based
// share encodes, but behind a slug so the visible URL stays compact.
// Uses Supabase PostgREST directly via fetch — no client SDK dependency.

import { SUPABASE_URL, SUPABASE_KEY, fetchWithTimeout, isSupabaseConfigured } from './supabase'
import { getSession, getValidAccessToken } from './auth'

const SLUG_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

// 12-char base62 ≈ 71.5 bits → ~3.2 quintillion possibilities. Doubles as
// URL secrecy since shares are publicly readable by slug. On collision we
// widen rather than retry at the same width, so the math degrades gracefully.
const generateSlug = (len: number): string => {
  const bytes = new Uint8Array(len)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => SLUG_CHARS[b % SLUG_CHARS.length]).join('')
}

// Slugs we generate match this shape; widened on collision but never wider
// than 14 chars. Used to reject malformed input before a wasted round-trip.
const SLUG_PATTERN = /^[A-Za-z0-9]{12,14}$/

// Build PostgREST headers. With a user JWT, PostgREST evaluates RLS as that
// user (authenticated role). Without one, it evaluates as anon.
const restHeaders = (userToken: string | null): HeadersInit => {
  const key = SUPABASE_KEY!
  return {
    apikey: key,
    Authorization: `Bearer ${userToken ?? key}`,
  }
}

export const isShareEnabled = isSupabaseConfigured

export interface CreateShareOptions {
  /** Sets shares.display_name. Only meaningful when logged in (anon shares
   *  are unlisted so a name has nowhere to surface). */
  displayName?: string
}

export const createShare = async (blob: unknown, opts: CreateShareOptions = {}): Promise<string> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('share backend not configured')

  const session = getSession()
  const token = session ? await getValidAccessToken() : null
  const userId = session && token ? session.user.id : null

  const baseRow: Record<string, unknown> = { blob }
  if (userId) {
    baseRow.user_id = userId
    if (opts.displayName) baseRow.display_name = opts.displayName
  }

  for (let attempt = 0; attempt < 3; attempt++) {
    const slug = generateSlug(12 + attempt)
    const res = await fetchWithTimeout(`${SUPABASE_URL}/rest/v1/shares`, {
      method: 'POST',
      headers: {
        ...restHeaders(token),
        'Content-Type': 'application/json',
        Prefer: 'return=minimal',
      },
      body: JSON.stringify({ ...baseRow, slug }),
    })
    if (res.ok) return slug
    if (res.status === 409) continue
    throw new Error(`share create failed: ${res.status} ${await res.text()}`)
  }
  throw new Error('share create failed: slug collisions exhausted')
}

export const loadShare = async (slug: string): Promise<unknown> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('share backend not configured')
  if (!SLUG_PATTERN.test(slug)) throw new Error('invalid share slug')

  const url = `${SUPABASE_URL}/rest/v1/shares?slug=eq.${encodeURIComponent(slug)}&select=blob`
  const res = await fetchWithTimeout(url, { headers: restHeaders(null) })
  if (!res.ok) throw new Error(`share load failed: ${res.status}`)
  const rows = (await res.json()) as Array<{ blob: unknown }>
  if (rows.length === 0) throw new Error('share not found')
  return rows[0].blob
}

export interface MyShare {
  slug: string
  display_name: string | null
  pinned: boolean
  created_at: string
  updated_at: string
}

export const listMyShares = async (): Promise<MyShare[]> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('share backend not configured')
  const session = getSession()
  if (!session) throw new Error('not signed in')
  const token = await getValidAccessToken()
  if (!token) throw new Error('session expired')

  const url = `${SUPABASE_URL}/rest/v1/shares?user_id=eq.${session.user.id}` +
    `&select=slug,display_name,pinned,created_at,updated_at&order=updated_at.desc`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`list shares failed: ${res.status}`)
  return (await res.json()) as MyShare[]
}

// Generic owner-only PATCH. RLS guarantees only the owner reaches Postgres.
interface MySharePatch {
  display_name?: string | null
  pinned?: boolean
}
const updateMyShare = async (slug: string, patch: MySharePatch): Promise<void> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('share backend not configured')
  if (!SLUG_PATTERN.test(slug)) throw new Error('invalid share slug')
  const token = await getValidAccessToken()
  if (!token) throw new Error('session expired')

  const url = `${SUPABASE_URL}/rest/v1/shares?slug=eq.${encodeURIComponent(slug)}`
  const res = await fetchWithTimeout(url, {
    method: 'PATCH',
    headers: {
      ...restHeaders(token),
      'Content-Type': 'application/json',
      Prefer: 'return=minimal',
    },
    body: JSON.stringify({ ...patch, updated_at: new Date().toISOString() }),
  })
  if (!res.ok) throw new Error(`update failed: ${res.status} ${await res.text()}`)
}

export const renameMyShare = (slug: string, displayName: string | null) =>
  updateMyShare(slug, { display_name: displayName })

export const pinMyShare = (slug: string, pinned: boolean) =>
  updateMyShare(slug, { pinned })

export const deleteMyShare = async (slug: string): Promise<void> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('share backend not configured')
  if (!SLUG_PATTERN.test(slug)) throw new Error('invalid share slug')
  const token = await getValidAccessToken()
  if (!token) throw new Error('session expired')

  const url = `${SUPABASE_URL}/rest/v1/shares?slug=eq.${encodeURIComponent(slug)}`
  const res = await fetchWithTimeout(url, {
    method: 'DELETE',
    headers: { ...restHeaders(token), Prefer: 'return=minimal' },
  })
  if (!res.ok) throw new Error(`delete failed: ${res.status} ${await res.text()}`)
}
