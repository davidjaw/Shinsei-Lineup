// Cloud-sync backend for 編組 (lineup groups). Companion to the localStorage
// autosave in useGroupPersistence.ts — local stays the session-level source
// of truth, this is the cross-device mirror.
//
// Conflict detection uses PostgREST's filter syntax as an etag-equivalent:
// PATCH calls send `&updated_at=eq.<iso-of-last-load>` plus
// `Prefer: return=representation`. A response body of `[]` means the
// precondition didn't match — the row was updated by another device since
// we last read it — and the caller surfaces a conflict dialog.
//
// Same PostgREST-via-fetch pattern as share.ts / profiles.ts.

import { SUPABASE_URL, fetchWithTimeout, restHeaders } from './supabase'
import { requireAuth } from './auth'
import type { ShareableLineup } from '../constants/gameData'

export interface CloudLineupGroup {
  id: string
  client_id: string | null
  name: string
  teams: ShareableLineup[]
  team_schema: number
  sort_order: number
  created_at: string
  updated_at: string
}

const COLS = 'id,client_id,name,teams,team_schema,sort_order,created_at,updated_at'

// Key-order independent JSON: jsonb does not keep key order, so a row read back
// from the server must serialize the same as the local copy it was written
// from. Keys in `omit` are dropped at every depth.
export const stableStringify = (value: unknown, omit?: ReadonlySet<string>): string => {
  const sorted = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(sorted)
    if (v === null || typeof v !== 'object') return v
    const out: Record<string, unknown> = {}
    for (const key of Object.keys(v).sort()) {
      if (!omit?.has(key)) out[key] = sorted((v as Record<string, unknown>)[key])
    }
    return out
  }
  return JSON.stringify(sorted(value)) ?? ''
}

// cyrb53: a fast synchronous hash, so a large group does not cost its full size
// in the persisted meta. Length is included to make collisions even less likely.
const hashString = (text: string): string => {
  let h1 = 0xdeadbeef
  let h2 = 0x41c6ce57
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i)
    h1 = Math.imul(h1 ^ c, 2654435761)
    h2 = Math.imul(h2 ^ c, 1597334677)
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909)
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909)
  const mixed = 4294967296 * (2097151 & h2) + (h1 >>> 0)
  return `${text.length.toString(36)}.${mixed.toString(36)}`
}

// The user-edited part of a row. sort_order is tracked apart from it, because a
// position shift caused by another group is not an edit of this one.
export const groupContentHash = (name: string, teams: ShareableLineup[]): string =>
  hashString(stableStringify({ name, teams }))

export const listMyLineupGroups = async (): Promise<CloudLineupGroup[]> => {
  const { userId, token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?user_id=eq.${userId}` +
    `&select=${COLS}&order=sort_order.asc,updated_at.desc`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`list lineup_groups failed: ${res.status}`)
  return (await res.json()) as CloudLineupGroup[]
}

export interface CreateLineupGroupInput {
  /** ShareableGroup.id from the local blob — used for idempotent retry via
   *  the (user_id, client_id) partial unique index. May be omitted only when
   *  the row originates cloud-first (no local snapshot to seed from). */
  client_id?: string
  name: string
  teams: ShareableLineup[]
  sort_order?: number
}

export interface CreatedLineupGroup {
  row: CloudLineupGroup
  /** True when the row already existed, so nothing from `input` was written.
   *  Its content may differ from the input; the caller must compare. */
  adopted: boolean
}

// A client_id collision on the (user_id, client_id) partial unique index may
// surface two ways. ignore-duplicates suppresses the INSERT and returns an empty
// body if it covers that index; otherwise the POST fails with 409, because the
// request names no conflict target and the primary key is `id`. Both mean the
// row already exists.
const isDuplicateResponse = (res: Response): boolean => res.status === 409

// Idempotent w.r.t. that index when client_id is provided: on a collision we GET
// by client_id so the caller always receives a populated CloudLineupGroup
// (existing or new) to hydrate its meta map. Without client_id, this is a plain
// INSERT.
export const createLineupGroup = async (
  input: CreateLineupGroupInput,
): Promise<CreatedLineupGroup> => {
  const { userId, token } = await requireAuth()
  const row: Record<string, unknown> = {
    user_id: userId,
    name: input.name,
    teams: input.teams,
    sort_order: input.sort_order ?? 0,
  }
  if (input.client_id) row.client_id = input.client_id

  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?select=${COLS}`
  const prefer = input.client_id
    ? 'return=representation,resolution=ignore-duplicates'
    : 'return=representation'
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: {
      ...restHeaders(token),
      'Content-Type': 'application/json',
      Prefer: prefer,
    },
    body: JSON.stringify(row),
  })
  const duplicate = Boolean(input.client_id) && isDuplicateResponse(res)
  if (!res.ok && !duplicate) {
    throw new Error(`create lineup_group failed: ${res.status} ${await res.text()}`)
  }
  const rows = duplicate ? [] : (await res.json()) as CloudLineupGroup[]
  if (rows.length > 0) return { row: rows[0], adopted: false }
  // A suppressed INSERT. Fetch the existing row so callers always get a usable
  // CloudLineupGroup back.
  if (!input.client_id) {
    throw new Error('create lineup_group: empty response with no client_id to recover from')
  }
  const existing = await getLineupGroupByClientId(input.client_id)
  if (!existing) {
    throw new Error(
      `create lineup_group: insert reported a duplicate but no row found for client_id=${input.client_id}`,
    )
  }
  return { row: existing, adopted: true }
}

// RLS scopes by user_id automatically, so this lookup naturally resolves to
// the current user's row. Used by createLineupGroup's empty-body recovery
// and by useGroupPersistence's meta-map heal-on-409 path.
const getLineupGroupByClientId = async (
  clientId: string,
): Promise<CloudLineupGroup | null> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?client_id=eq.${encodeURIComponent(clientId)}` +
    `&select=${COLS}`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`get lineup_group by client_id failed: ${res.status}`)
  const rows = (await res.json()) as CloudLineupGroup[]
  return rows[0] ?? null
}

// Bulk insert used by the anon→signed-in handoff when local has groups and
// cloud is empty. Returns only the rows it inserted; a short result means some
// inputs collided with existing rows. A 409 fails the whole array, so retry one
// at a time to get the same result as a suppressed duplicate.
export const bulkCreateLineupGroups = async (
  inputs: CreateLineupGroupInput[],
): Promise<CloudLineupGroup[]> => {
  if (inputs.length === 0) return []
  const { userId, token } = await requireAuth()
  const rows = inputs.map((input, idx) => {
    const row: Record<string, unknown> = {
      user_id: userId,
      name: input.name,
      teams: input.teams,
      sort_order: input.sort_order ?? idx,
    }
    if (input.client_id) row.client_id = input.client_id
    return row
  })

  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?select=${COLS}`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: {
      ...restHeaders(token),
      'Content-Type': 'application/json',
      Prefer: 'return=representation,resolution=ignore-duplicates',
    },
    body: JSON.stringify(rows),
  })
  if (isDuplicateResponse(res)) {
    const results = []
    for (const input of inputs) results.push(await createLineupGroup(input))
    return results.filter((r) => !r.adopted).map((r) => r.row)
  }
  if (!res.ok) {
    throw new Error(`bulk create lineup_groups failed: ${res.status} ${await res.text()}`)
  }
  return (await res.json()) as CloudLineupGroup[]
}

export interface LineupGroupPatch {
  name?: string
  teams?: ShareableLineup[]
  sort_order?: number
}

export type PatchResult =
  | { kind: 'ok'; row: CloudLineupGroup }
  | { kind: 'conflict'; serverRow: CloudLineupGroup }
  | { kind: 'deleted' }
  | { kind: 'error'; message: string }

// Optimistic-lock PATCH. expectedUpdatedAt is the ISO string returned by the
// last successful read/write of this row. If the server has a newer
// updated_at, the filter doesn't match, PostgREST returns 0 rows, and the
// caller gets `kind: 'conflict'` along with the current server row so they
// can show a 3-option dialog (use cloud / overwrite cloud / defer).
export const patchLineupGroupWithLock = async (
  id: string,
  expectedUpdatedAt: string,
  patch: LineupGroupPatch,
): Promise<PatchResult> => {
  const { token } = await requireAuth()
  // The trigger maintains updated_at server-side; we don't include it in the
  // body. The filter is the precondition.
  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?id=eq.${encodeURIComponent(id)}` +
    `&updated_at=eq.${encodeURIComponent(expectedUpdatedAt)}` +
    `&select=${COLS}`
  try {
    const res = await fetchWithTimeout(url, {
      method: 'PATCH',
      headers: {
        ...restHeaders(token),
        'Content-Type': 'application/json',
        Prefer: 'return=representation',
      },
      body: JSON.stringify(patch),
    })
    if (!res.ok) {
      return { kind: 'error', message: `${res.status} ${await res.text()}` }
    }
    const rows = (await res.json()) as CloudLineupGroup[]
    if (rows.length > 0) {
      return { kind: 'ok', row: rows[0] }
    }
    // 0-row PATCH response: either the precondition failed (conflict) or the
    // row was deleted. Fetch the current row to disambiguate.
    const serverRow = await getLineupGroup(id)
    if (!serverRow) {
      return { kind: 'deleted' }
    }
    return { kind: 'conflict', serverRow }
  } catch (e) {
    return { kind: 'error', message: (e as Error).message }
  }
}

// Force PATCH without the precondition — used by "overwrite cloud" in the
// conflict dialog. The user has just seen what they're discarding. Returns null
// when the row no longer exists.
export const patchLineupGroupForce = async (
  id: string,
  patch: LineupGroupPatch,
): Promise<CloudLineupGroup | null> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?id=eq.${encodeURIComponent(id)}` +
    `&select=${COLS}`
  const res = await fetchWithTimeout(url, {
    method: 'PATCH',
    headers: {
      ...restHeaders(token),
      'Content-Type': 'application/json',
      Prefer: 'return=representation',
    },
    body: JSON.stringify(patch),
  })
  if (!res.ok) {
    throw new Error(`force patch failed: ${res.status} ${await res.text()}`)
  }
  const rows = (await res.json()) as CloudLineupGroup[]
  return rows[0] ?? null
}

const getLineupGroup = async (id: string): Promise<CloudLineupGroup | null> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?id=eq.${encodeURIComponent(id)}` +
    `&select=${COLS}`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`get lineup_group failed: ${res.status}`)
  const rows = (await res.json()) as CloudLineupGroup[]
  return rows[0] ?? null
}

export const deleteLineupGroup = async (id: string): Promise<void> => {
  const { token } = await requireAuth()
  const url = `${SUPABASE_URL}/rest/v1/lineup_groups?id=eq.${encodeURIComponent(id)}`
  const res = await fetchWithTimeout(url, {
    method: 'DELETE',
    headers: { ...restHeaders(token), Prefer: 'return=minimal' },
  })
  if (!res.ok) {
    throw new Error(`delete lineup_group failed: ${res.status} ${await res.text()}`)
  }
}
