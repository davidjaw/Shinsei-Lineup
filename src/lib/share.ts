// Short-URL share backend. Stores the same payload that the legacy hash-based
// share encodes, but behind a slug so the visible URL stays compact.
// Uses Supabase PostgREST directly via fetch — no client SDK dependency.

import { SUPABASE_URL, SUPABASE_KEY, fetchWithTimeout, isSupabaseConfigured, restHeaders } from './supabase'
import { getSession, getValidAccessToken } from './auth'

const SLUG_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

// 12-char base62 ≈ 71.5 bits → ~3.2 quintillion possibilities. Doubles as
// URL secrecy since a share is readable by anyone holding its slug. On collision we
// widen rather than retry at the same width, so the math degrades gracefully.
const generateSlug = (len: number): string => {
  const bytes = new Uint8Array(len)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => SLUG_CHARS[b % SLUG_CHARS.length]).join('')
}

// Slugs we generate match this shape; widened on collision but never wider
// than 14 chars. Used to reject malformed input before a wasted round-trip.
const SLUG_PATTERN = /^[A-Za-z0-9]{12,14}$/

export const isShareEnabled = isSupabaseConfigured

export const SHARE_KINDS = ['lineup', 'group', 'inventory', 'profile', 'gacha_log'] as const
export type ShareKind = typeof SHARE_KINDS[number]

export const SHARE_KIND_LABELS: Record<ShareKind, string> = {
  lineup: '單隊',
  group: '編組',
  inventory: '庫存',
  profile: '角色配置',
  gacha_log: '抽卡紀錄',
}

export interface CreateShareOptions {
  /** Sets shares.display_name. Only meaningful when logged in (anon shares
   *  are unlisted so a name has nowhere to surface). */
  displayName?: string
  /** Required discriminator written to shares.kind. Drives the type column
   *  in 我的分享 without needing to inspect blob shape on the list side. */
  kind: ShareKind
}

export const createShare = async (blob: unknown, opts: CreateShareOptions): Promise<string> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('share backend not configured')

  const session = getSession()
  const token = session ? await getValidAccessToken() : null
  const userId = session && token ? session.user.id : null

  const baseRow: Record<string, unknown> = { blob, kind: opts.kind }
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

  const res = await fetchWithTimeout(`${SUPABASE_URL}/rest/v1/rpc/share_blob`, {
    method: 'POST',
    headers: { ...restHeaders(null), 'Content-Type': 'application/json' },
    body: JSON.stringify({ p_slug: slug }),
  })
  if (!res.ok) throw new Error(`share load failed: ${res.status}`)
  const blob: unknown = await res.json()
  if (blob === null) throw new Error('share not found')
  return blob
}

export type ShareSource = { slug: string } | { base64: string }

/** Throws on anything that is not base64 of UTF-8 JSON. */
export const decodeShareBlob = (base64: string): unknown =>
  JSON.parse(decodeURIComponent(escape(atob(base64))))

const decodesToObject = (base64: string): boolean => {
  try {
    const value = decodeShareBlob(base64)
    return typeof value === 'object' && value !== null
  } catch {
    return false
  }
}

const percentDecoded = (part: string): string | null => {
  try {
    return decodeURIComponent(part)
  } catch {
    return null
  }
}

/**
 * What a pasted text points at: a slug alone, or a link of either site in any of
 * its forms (`#s/<slug>`, `#/s/<slug>`, `#<base64>`, `#/<base64>`, and the new
 * site's `#/lineup/s/<slug>`, `#/lineup/b/<percent-encoded base64>`). Null if none.
 * The payload is tried first: base64 may itself hold `s/`.
 */
export const parseShareInput = (text: string): ShareSource | null => {
  const input = text.trim()
  if (!input) return null
  if (SLUG_PATTERN.test(input)) return { slug: input }
  const payload = input.slice(input.indexOf('#') + 1).replace(/^\//, '')
  if (decodesToObject(payload)) return { base64: payload }
  const slug = /(?:^|[/#])s\/([A-Za-z0-9]{12,14})(?:[/?#&]|$)/.exec(input)
  if (slug) return { slug: slug[1] }
  const blob = /(?:^|[/#])b\/([^?#&\s]+)/.exec(input)
  const decoded = blob && percentDecoded(blob[1])
  return decoded && decodesToObject(decoded) ? { base64: decoded } : null
}

/** The blob a pasted text points at. Null when the text points at nothing. */
export const loadShareSource = async (text: string): Promise<unknown> => {
  const source = parseShareInput(text)
  if (!source) return null
  return 'slug' in source ? loadShare(source.slug) : decodeShareBlob(source.base64)
}

export interface MyShare {
  slug: string
  display_name: string | null
  pinned: boolean
  kind: ShareKind
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
    `&select=slug,display_name,pinned,kind,created_at,updated_at&order=updated_at.desc`
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
