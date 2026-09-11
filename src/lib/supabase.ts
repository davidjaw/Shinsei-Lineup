// Shared Supabase infrastructure used by share + auth modules.
// We talk to PostgREST + GoTrue directly via fetch — no SDK dependency.

export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL
export const SUPABASE_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

const FETCH_TIMEOUT_MS = 8000

// Promotes silent network hangs (slow Supabase, captive portal, dead DNS) into
// a fast caught error so callers don't await past the browser's TCP timeout.
export const fetchWithTimeout = async (
  url: string,
  init: RequestInit = {},
  timeoutMs = FETCH_TIMEOUT_MS,
): Promise<Response> => {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: ctrl.signal })
  } finally {
    clearTimeout(timer)
  }
}

export const isSupabaseConfigured = (): boolean => Boolean(SUPABASE_URL && SUPABASE_KEY)

// PostgREST auth headers. Pass null/undefined to call as anon (unauthenticated
// reads via RLS public policies). Pass a JWT to call as the authenticated user.
export const restHeaders = (userToken: string | null): HeadersInit => {
  const key = SUPABASE_KEY!
  return {
    apikey: key,
    Authorization: `Bearer ${userToken ?? key}`,
  }
}
