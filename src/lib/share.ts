// Short-URL share backend. Stores the same payload that the legacy hash-based
// share encodes, but behind a slug so the visible URL stays compact.
// Uses Supabase PostgREST directly via fetch — no client SDK dependency.

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
const SUPABASE_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

const SLUG_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

// 12-char base62 ≈ 71.5 bits → ~3.2 quintillion possibilities. Doubles as
// URL secrecy since shares are publicly readable by slug. On collision we
// widen rather than retry at the same width, so the math degrades gracefully.
const generateSlug = (len: number): string => {
  const bytes = new Uint8Array(len)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => SLUG_CHARS[b % SLUG_CHARS.length]).join('')
}

const authHeaders = (key: string): HeadersInit => ({
  apikey: key,
  Authorization: `Bearer ${key}`,
})

// Promote silent network hangs (slow Supabase, captive portal, etc.) into a
// fast caught error so initFromHash doesn't leave the user staring at a blank
// default state for the browser's TCP timeout (~90s).
const FETCH_TIMEOUT_MS = 8000
const fetchWithTimeout = async (url: string, init: RequestInit): Promise<Response> => {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS)
  try {
    return await fetch(url, { ...init, signal: ctrl.signal })
  } finally {
    clearTimeout(timer)
  }
}

// Slugs we generate match this shape; widened on collision but never wider
// than 14 chars. Used to reject malformed input before a wasted round-trip.
const SLUG_PATTERN = /^[A-Za-z0-9]{12,14}$/

export const isShareEnabled = (): boolean => Boolean(SUPABASE_URL && SUPABASE_KEY)

export const createShare = async (blob: unknown): Promise<string> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('share backend not configured')

  for (let attempt = 0; attempt < 3; attempt++) {
    const slug = generateSlug(12 + attempt)
    const res = await fetchWithTimeout(`${SUPABASE_URL}/rest/v1/shares`, {
      method: 'POST',
      headers: {
        ...authHeaders(SUPABASE_KEY),
        'Content-Type': 'application/json',
        Prefer: 'return=minimal',
      },
      body: JSON.stringify({ slug, blob }),
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
  const res = await fetchWithTimeout(url, { headers: authHeaders(SUPABASE_KEY) })
  if (!res.ok) throw new Error(`share load failed: ${res.status}`)
  const rows = (await res.json()) as Array<{ blob: unknown }>
  if (rows.length === 0) throw new Error('share not found')
  return rows[0].blob
}
