// Character profile backend. A "profile" is a named, cloud-synced inventory
// (owned heroes + skills) — lets one user keep multiple card sets (main / alt
// account, helping a friend configure their roster, etc.). Lineups are NOT
// tied to a profile; they live in the active session only.
//
// Same PostgREST-via-fetch pattern as share.ts.

import { SUPABASE_URL, SUPABASE_KEY, fetchWithTimeout, isSupabaseConfigured } from './supabase'
import { getSession, getValidAccessToken } from './auth'

const restHeaders = (userToken: string): HeadersInit => ({
  apikey: SUPABASE_KEY!,
  Authorization: `Bearer ${userToken}`,
})

export const isProfilesEnabled = isSupabaseConfigured

export interface Profile {
  id: string
  name: string
  inv_h: string[]              // JP names — stable across translation revisions
  inv_s: string[]
  is_default: boolean
  created_at: string
  updated_at: string
}

const requireAuth = async (): Promise<{ userId: string; token: string }> => {
  if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error('profiles backend not configured')
  const session = getSession()
  if (!session) throw new Error('not signed in')
  const token = await getValidAccessToken()
  if (!token) throw new Error('session expired')
  return { userId: session.user.id, token }
}

export const listMyProfiles = async (): Promise<Profile[]> => {
  const { userId, token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/character_profiles?user_id=eq.${userId}` +
    `&select=id,name,inv_h,inv_s,is_default,created_at,updated_at` +
    `&order=is_default.desc,updated_at.desc`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`list profiles failed: ${res.status}`)
  return (await res.json()) as Profile[]
}

export interface CreateProfileInput {
  name: string
  inv_h: string[]
  inv_s: string[]
  is_default?: boolean
}

export const createProfile = async (input: CreateProfileInput): Promise<Profile> => {
  const { userId, token } = await requireAuth()
  const row = {
    user_id: userId,
    name: input.name,
    inv_h: input.inv_h,
    inv_s: input.inv_s,
    is_default: input.is_default ?? false,
  }
  const url = `${SUPABASE_URL}/rest/v1/character_profiles?select=id,name,inv_h,inv_s,is_default,created_at,updated_at`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json', Prefer: 'return=representation' },
    body: JSON.stringify(row),
  })
  if (!res.ok) throw new Error(`create profile failed: ${res.status} ${await res.text()}`)
  const rows = (await res.json()) as Profile[]
  return rows[0]
}

interface ProfilePatch {
  name?: string
  inv_h?: string[]
  inv_s?: string[]
  is_default?: boolean
}

const patchProfile = async (id: string, patch: ProfilePatch): Promise<void> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/character_profiles?id=eq.${encodeURIComponent(id)}`
  const res = await fetchWithTimeout(url, {
    method: 'PATCH',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json', Prefer: 'return=minimal' },
    body: JSON.stringify({ ...patch, updated_at: new Date().toISOString() }),
  })
  if (!res.ok) throw new Error(`update profile failed: ${res.status} ${await res.text()}`)
}

export const renameProfile = (id: string, name: string) => patchProfile(id, { name })

export const updateProfileInventory = (id: string, inv_h: string[], inv_s: string[]) =>
  patchProfile(id, { inv_h, inv_s })

// Clear the is_default flag on every profile owned by this user. RLS scopes
// the bulk PATCH to the caller's rows, so PostgREST's filter-then-PATCH does
// it in a single round-trip rather than one-by-one.
const clearAllDefaults = async (): Promise<void> => {
  const { userId, token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/character_profiles?user_id=eq.${userId}&is_default=eq.true`
  const res = await fetchWithTimeout(url, {
    method: 'PATCH',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json', Prefer: 'return=minimal' },
    body: JSON.stringify({ is_default: false, updated_at: new Date().toISOString() }),
  })
  if (!res.ok) throw new Error(`clear default failed: ${res.status}`)
}

// Two-step toggle (no DB trigger): unset all current defaults, then set the
// chosen one. Pass null to leave no profile marked as default.
export const setDefaultProfile = async (id: string | null): Promise<void> => {
  await clearAllDefaults()
  if (id !== null) await patchProfile(id, { is_default: true })
}

export const deleteProfile = async (id: string): Promise<void> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/character_profiles?id=eq.${encodeURIComponent(id)}`
  const res = await fetchWithTimeout(url, {
    method: 'DELETE',
    headers: { ...restHeaders(token), Prefer: 'return=minimal' },
  })
  if (!res.ok) throw new Error(`delete profile failed: ${res.status} ${await res.text()}`)
}
