// Account-ban REST helpers. Self-read via RLS; writes go through admin RPCs.

import { SUPABASE_URL, fetchWithTimeout, restHeaders } from './supabase'
import { getSession, getValidAccessToken } from './auth'
import { mapRpcError } from './variants'

export async function fetchMyBan(): Promise<boolean> {
  if (!SUPABASE_URL) return false
  const token = await getValidAccessToken()
  const session = getSession()
  if (!token || !session) return false

  const res = await fetchWithTimeout(
    `${SUPABASE_URL}/rest/v1/user_bans`
      + `?user_id=eq.${encodeURIComponent(session.user.id)}`
      + `&select=user_id`,
    { headers: restHeaders(token) },
  )
  if (!res.ok) return false
  const rows = (await res.json()) as Array<{ user_id: string }>
  return rows.length > 0
}

export async function adminListBannedUserIds(): Promise<string[]> {
  if (!SUPABASE_URL) throw new Error('bans backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('請先登入')

  const res = await fetchWithTimeout(
    `${SUPABASE_URL}/rest/v1/rpc/admin_list_banned_users`,
    {
      method: 'POST',
      headers: { ...restHeaders(token), 'Content-Type': 'application/json' },
      body: '{}',
    },
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(mapRpcError(body, `admin_list_banned_users failed: ${res.status} ${body}`))
  }
  const rows = await res.json() as unknown
  if (!Array.isArray(rows)) return []
  return rows.map((row) => {
    if (typeof row === 'string') return row
    if (row && typeof row === 'object') {
      const v = (row as { admin_list_banned_users?: unknown; user_id?: unknown })
      if (typeof v.admin_list_banned_users === 'string') return v.admin_list_banned_users
      if (typeof v.user_id === 'string') return v.user_id
    }
    return null
  }).filter((id): id is string => id != null)
}

export async function adminSetUserBanned(input: {
  userId: string
  banned: boolean
  reason?: string | null
}): Promise<{ ok: true; banned: boolean }> {
  if (!SUPABASE_URL) throw new Error('bans backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('請先登入')

  const res = await fetchWithTimeout(
    `${SUPABASE_URL}/rest/v1/rpc/admin_set_user_banned`,
    {
      method: 'POST',
      headers: { ...restHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        p_user_id: input.userId,
        p_banned: input.banned,
        p_reason: input.reason ?? null,
      }),
    },
  )
  if (!res.ok) {
    const body = await res.text()
    throw new Error(mapRpcError(body, `admin_set_user_banned failed: ${res.status} ${body}`))
  }
  const body = await res.json() as { ok: boolean; banned: boolean }
  return { ok: true, banned: body.banned }
}
