// OAuth (Google + GitHub) via Supabase GoTrue, no SDK.
// Implicit flow: full-page redirect → provider → back to SPA with tokens in
// the URL hash. handleAuthCallback() must run before any other hash-based
// router logic so we don't mistake an auth callback for a share link.

import { SUPABASE_URL, SUPABASE_KEY, fetchWithTimeout } from './supabase'

export type OAuthProvider = 'google' | 'github'

export interface Session {
  access_token: string
  refresh_token: string
  expires_at: number  // unix seconds
  user: {
    id: string
    email: string
  }
}

const SESSION_KEY = 'nobunaga.auth.session'
// Refresh ~1 minute before expiry so a long action doesn't 401 mid-flight.
const REFRESH_LEEWAY_SEC = 60

// Decode (NOT verify) a JWT payload. Safe because Supabase already validated
// the token before issuing it; we only read it to display user info.
const decodeJwtPayload = (token: string): { sub: string; email?: string } | null => {
  try {
    const part = token.split('.')[1]
    const padded = part + '='.repeat((4 - (part.length % 4)) % 4)
    return JSON.parse(atob(padded.replace(/-/g, '+').replace(/_/g, '/')))
  } catch {
    return null
  }
}

const persistSession = (session: Session): void => {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

const clearSession = (): void => {
  localStorage.removeItem(SESSION_KEY)
}

export const getSession = (): Session | null => {
  const raw = localStorage.getItem(SESSION_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Session
  } catch {
    clearSession()
    return null
  }
}

// Initiate OAuth — full-page redirect away from the SPA.
// Provider returns to ${origin}${pathname} with tokens in the hash; we capture
// them via handleAuthCallback on the next page load.
export const signInWithProvider = (provider: OAuthProvider): void => {
  if (!SUPABASE_URL) throw new Error('auth not configured')
  const redirectTo = `${location.origin}${location.pathname}`
  const url = `${SUPABASE_URL}/auth/v1/authorize?provider=${provider}&redirect_to=${encodeURIComponent(redirectTo)}`
  location.assign(url)
}

// Returns true if the hash was an auth callback we consumed (and cleared).
// Throws if the callback indicates a provider-side error (cancelled, denied).
export const handleAuthCallback = (): boolean => {
  const hash = location.hash.slice(1)
  if (!hash || (!hash.includes('access_token=') && !hash.includes('error='))) {
    return false
  }

  const params = new URLSearchParams(hash)
  const cleanHash = () => history.replaceState(null, '', location.pathname + location.search)

  const error = params.get('error')
  if (error) {
    cleanHash()
    throw new Error(params.get('error_description') || error)
  }

  const access_token = params.get('access_token')
  const refresh_token = params.get('refresh_token')
  const expires_in = parseInt(params.get('expires_in') || '0', 10)

  if (!access_token || !refresh_token) {
    cleanHash()
    throw new Error('incomplete auth callback')
  }

  const payload = decodeJwtPayload(access_token)
  if (!payload?.sub) {
    cleanHash()
    throw new Error('malformed access token')
  }

  persistSession({
    access_token,
    refresh_token,
    expires_at: Math.floor(Date.now() / 1000) + expires_in,
    user: { id: payload.sub, email: payload.email || '' },
  })
  cleanHash()
  return true
}

// Exchange the refresh_token for a new access_token. Returns the refreshed
// session, or null if refresh fails (refresh_token expired / revoked).
const refreshSession = async (refresh_token: string): Promise<Session | null> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) return null

  try {
    const res = await fetchWithTimeout(
      `${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`,
      {
        method: 'POST',
        headers: { apikey: SUPABASE_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token }),
      },
    )
    if (!res.ok) return null
    const data = (await res.json()) as {
      access_token: string
      refresh_token: string
      expires_in: number
      user?: { id: string; email?: string }
    }
    const payload = decodeJwtPayload(data.access_token)
    const id = data.user?.id ?? payload?.sub
    if (!id) return null

    const session: Session = {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_at: Math.floor(Date.now() / 1000) + data.expires_in,
      user: { id, email: data.user?.email ?? payload?.email ?? '' },
    }
    persistSession(session)
    return session
  } catch {
    return null
  }
}

// Returns a usable access token, refreshing if necessary. Returns null if
// there's no session, or if refresh failed (in which case session is cleared).
export const getValidAccessToken = async (): Promise<string | null> => {
  const session = getSession()
  if (!session) return null

  const now = Math.floor(Date.now() / 1000)
  if (session.expires_at - now > REFRESH_LEEWAY_SEC) {
    return session.access_token
  }

  const refreshed = await refreshSession(session.refresh_token)
  if (!refreshed) {
    clearSession()
    return null
  }
  return refreshed.access_token
}

// Best-effort server-side logout. Clears local state regardless of network
// outcome — user pressed Sign Out and expects to be logged out.
export const signOut = async (): Promise<void> => {
  const session = getSession()
  if (session && SUPABASE_URL && SUPABASE_KEY) {
    try {
      await fetchWithTimeout(`${SUPABASE_URL}/auth/v1/logout`, {
        method: 'POST',
        headers: {
          apikey: SUPABASE_KEY,
          Authorization: `Bearer ${session.access_token}`,
        },
      })
    } catch {
      // network failure shouldn't block sign-out
    }
  }
  clearSession()
}
