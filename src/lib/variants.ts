// Supabase REST client for the variant-first 精選隊伍 feature.
//
// In the new model, a variant is a canonical (HeroSet + skills + 兵學 + breakthrough)
// fingerprint — multiple users submitting the same team configuration collapse
// into a single variant row. Votes attach to variants; per-user submission
// attempts are tracked in variant_contributors.
//
// Server-side hashing: the client never computes hashes. submit_variant takes
// a team_blob, the RPC hashes it, upserts on conflict by variant_hash, and
// returns the canonical id.

import { SUPABASE_URL, fetchWithTimeout, isSupabaseConfigured, restHeaders } from './supabase'
import { getSession, getValidAccessToken } from './auth'
import type { Lineup } from '../composables/useLineups'

export type VoteDirection = 1 | -1

export const isVariantsEnabled = isSupabaseConfigured

// ---------------------------------------------------------------------------
// Wire types (DB row shapes). Kept private; map to TS-facing shapes below.

interface HeroSetRowDB {
  hero_set_hash: string
  sample_variant_id: string
  sample_team_blob: unknown
  variant_count: number | string
  total_vote_count: number | string
  total_upvote_count: number | string
  last_active_at: string
  recent_vote_delta: number | string
}

interface VariantRowDB {
  id: string
  variant_hash: string
  hero_set_hash: string
  team_blob: unknown
  first_author: string | null
  first_submitted_at: string
  vote_count: number
  upvote_count: number
  downvote_count: number
  created_at: string
  updated_at: string
}

interface ContributorRowDB {
  variant_id: string
  user_id: string
  contributed_at: string
  author_name: string | null
  team_name: string | null
  team_name_hidden: boolean
  team_name_locked: boolean
  author_name_hidden: boolean
  author_name_locked: boolean
}

// ---------------------------------------------------------------------------
// Exported shapes used by composables / views.

export interface HeroSetSummary {
  heroSetHash: string
  sampleVariantId: string
  sampleTeam: Lineup
  variantCount: number
  totalVoteCount: number
  totalUpvoteCount: number
  lastActiveAt: string
  recentVoteDelta: number
}

export interface Variant {
  id: string
  variantHash: string
  heroSetHash: string
  team: Lineup
  firstAuthorId: string | null
  firstSubmittedAt: string
  voteCount: number
  upvoteCount: number
  downvoteCount: number
  createdAt: string
  updatedAt: string
}

export interface VariantContributor {
  variantId: string
  userId: string
  contributedAt: string
  authorName: string | null
  teamName: string | null
  teamNameHidden: boolean
  teamNameLocked: boolean
  authorNameHidden: boolean
  authorNameLocked: boolean
}

export interface SubmitVariantResult {
  variantId: string
  variantHash: string
  heroSetHash: string
  isNew: boolean
}

// Coerce server-side bigint columns (which arrive as JSON strings) to numbers.
// PostgREST returns counts from a function-as-table as strings because BIGINT
// has no JSON-number-safe representation.
const num = (v: number | string | null | undefined): number =>
  v == null ? 0 : (typeof v === 'number' ? v : Number(v) || 0)

const rowToHeroSet = (row: HeroSetRowDB): HeroSetSummary => ({
  heroSetHash:      row.hero_set_hash,
  sampleVariantId:  row.sample_variant_id,
  sampleTeam:       row.sample_team_blob as Lineup,
  variantCount:     num(row.variant_count),
  totalVoteCount:   num(row.total_vote_count),
  totalUpvoteCount: num(row.total_upvote_count),
  lastActiveAt:     row.last_active_at,
  recentVoteDelta:  num(row.recent_vote_delta),
})

const rowToVariant = (row: VariantRowDB): Variant => ({
  id:                row.id,
  variantHash:       row.variant_hash,
  heroSetHash:       row.hero_set_hash,
  team:              row.team_blob as Lineup,
  firstAuthorId:     row.first_author,
  firstSubmittedAt:  row.first_submitted_at,
  voteCount:         row.vote_count,
  upvoteCount:       row.upvote_count ?? 0,
  downvoteCount:     row.downvote_count ?? 0,
  createdAt:         row.created_at,
  updatedAt:         row.updated_at,
})

const rowToContributor = (row: ContributorRowDB): VariantContributor => ({
  variantId:         row.variant_id,
  userId:            row.user_id,
  contributedAt:     row.contributed_at,
  authorName:        row.author_name,
  teamName:          row.team_name ?? null,
  teamNameHidden:    row.team_name_hidden ?? false,
  teamNameLocked:    row.team_name_locked ?? false,
  authorNameHidden:  row.author_name_hidden ?? false,
  authorNameLocked:  row.author_name_locked ?? false,
})

// ---------------------------------------------------------------------------
// Level-1 listing: aggregated HeroSet summaries for the grid.

export const listHeroSets = async (limit = 60, offset = 0): Promise<HeroSetSummary[]> => {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const url = `${SUPABASE_URL}/rest/v1/rpc/list_hero_sets`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(null), 'Content-Type': 'application/json' },
    body: JSON.stringify({ p_limit: limit, p_offset: offset }),
  })
  if (!res.ok) throw new Error(`list_hero_sets failed: ${res.status} ${await res.text()}`)
  const rows = (await res.json()) as HeroSetRowDB[]
  return rows.map(rowToHeroSet)
}

// ---------------------------------------------------------------------------
// Level-2 listing: every variant in a given HeroSet. Sort by `vote_count` for
// vote-rank, or by `updated_at` for "latest". Returned in whichever order the
// caller specifies via PostgREST's order parameter.

export type VariantSort = 'votes' | 'latest'

export const listVariantsInSet = async (
  heroSetHash: string,
  sort: VariantSort = 'votes',
): Promise<Variant[]> => {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const orderClause = sort === 'votes'
    ? 'vote_count.desc,updated_at.desc'
    : 'updated_at.desc,vote_count.desc'

  const url = `${SUPABASE_URL}/rest/v1/team_variants`
    + `?hero_set_hash=eq.${encodeURIComponent(heroSetHash)}`
    + `&select=*&order=${orderClause}`
  const res = await fetchWithTimeout(url, { headers: restHeaders(null) })
  if (!res.ok) throw new Error(`list variants failed: ${res.status}`)
  return ((await res.json()) as VariantRowDB[]).map(rowToVariant)
}

// Fetch every contributor for a variant. Used to render the "also submitted
// by N users" line + the contributor tooltip.
export const listContributors = async (variantId: string): Promise<VariantContributor[]> => {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const url = `${SUPABASE_URL}/rest/v1/variant_contributors_read`
    + `?variant_id=eq.${encodeURIComponent(variantId)}`
    + `&select=*&order=contributed_at.asc`
  const res = await fetchWithTimeout(url, { headers: restHeaders(null) })
  if (!res.ok) throw new Error(`contributors fetch failed: ${res.status}`)
  return ((await res.json()) as ContributorRowDB[]).map(rowToContributor)
}

// ---------------------------------------------------------------------------
// Mutations.

export const findVariantForTeam = async (team: Lineup): Promise<string | null> => {
  if (!SUPABASE_URL) return null
  const url = `${SUPABASE_URL}/rest/v1/rpc/find_variant_for_team`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(null), 'Content-Type': 'application/json' },
    body: JSON.stringify({ p_team: team }),
  })
  if (!res.ok) return null
  const body = await res.json()
  return typeof body === 'string' ? body : null
}

export const submitVariant = async (
  team: Lineup,
  authorName: string | null,
  teamName?: string | null,
): Promise<SubmitVariantResult> => {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('login required to publish a variant')

  const url = `${SUPABASE_URL}/rest/v1/rpc/submit_variant`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      p_team: team,
      p_author_name: authorName,
      p_team_name: teamName ?? null,
    }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(mapRpcError(body, `submit_variant failed: ${res.status} ${body}`))
  }
  const body = await res.json() as {
    variant_id: string
    variant_hash: string
    hero_set_hash: string
    is_new: boolean
  }
  return {
    variantId:     body.variant_id,
    variantHash:   body.variant_hash,
    heroSetHash:   body.hero_set_hash,
    isNew:         body.is_new,
  }
}

export type ReportKind = 'team_name' | 'display_name'

const REPORT_PG_ERRORS: Record<string, string> = {
  'auth required': '請先登入',
  'cannot report yourself': '不能檢舉自己',
  'target is not a contributor': '找不到檢舉對象',
  'account banned': '此帳號已被封鎖，無法公開分享',
  'cannot ban yourself': '不能封鎖自己',
  'admin required': '需要管理員權限',
}

export const mapRpcError = (body: string, fallback: string): string => {
  try {
    const parsed = JSON.parse(body) as { message?: string }
    const mapped = parsed.message ? REPORT_PG_ERRORS[parsed.message] : undefined
    if (mapped) return mapped
  } catch { /* not JSON */ }
  for (const [pg, zh] of Object.entries(REPORT_PG_ERRORS)) {
    if (body.includes(pg)) return zh
  }
  return fallback
}

const mapReportError = mapRpcError

export async function reportContent(input: {
  kind: ReportKind
  variantId: string | null
  targetUserId: string
}): Promise<{ ok: true; hidden: boolean; alreadyReported: boolean }> {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('請先登入')

  const url = `${SUPABASE_URL}/rest/v1/rpc/report_content`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      p_kind: input.kind,
      p_variant_id: input.variantId,
      p_target_user_id: input.targetUserId,
    }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(mapReportError(body, `report_content failed: ${res.status} ${body}`))
  }
  const body = await res.json() as {
    ok: boolean
    hidden: boolean
    already_reported: boolean
  }
  return {
    ok: true,
    hidden: body.hidden,
    alreadyReported: body.already_reported,
  }
}

export async function adminSetNameHidden(input: {
  kind: ReportKind
  variantId: string | null
  targetUserId: string
  hidden: boolean
  locked?: boolean
}): Promise<{ ok: true; hidden: boolean; locked: boolean }> {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('請先登入')

  const url = `${SUPABASE_URL}/rest/v1/rpc/admin_set_name_hidden`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      p_kind: input.kind,
      p_variant_id: input.variantId,
      p_target_user_id: input.targetUserId,
      p_hidden: input.hidden,
      p_locked: input.locked ?? false,
    }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(mapRpcError(body, `admin_set_name_hidden failed: ${res.status} ${body}`))
  }
  const body = await res.json() as { ok: boolean; hidden: boolean; locked: boolean }
  return { ok: true, hidden: body.hidden, locked: body.locked }
}

// Withdraw the current user from a variant. The RPC returns three flags:
//   - deleted:     variant row was removed (caller was last contributor, or
//                  variant no longer existed when called)
//   - transferred: first_author credit moved to another contributor (only
//                  true when the caller was the previous first_author and
//                  other contributors remained)
//   - firstAuthor: the new first_author when transferred=true; absent otherwise
export const withdrawVariant = async (
  variantId: string,
): Promise<{ deleted: boolean; transferred: boolean; firstAuthor: string | null }> => {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('login required')

  const url = `${SUPABASE_URL}/rest/v1/rpc/withdraw_variant`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { ...restHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ p_variant_id: variantId }),
  })
  if (!res.ok) throw new Error(`withdraw_variant failed: ${res.status} ${await res.text()}`)
  const body = await res.json() as {
    deleted: boolean
    transferred: boolean
    first_author?: string | null
  }
  return {
    deleted: body.deleted,
    transferred: body.transferred,
    firstAuthor: body.transferred ? (body.first_author ?? null) : null,
  }
}

// Mirrors the proposal_votes upsert pattern: insert-or-flip via PostgREST
// resolution=merge-duplicates against the (variant_id, user_id) PK.
export const setVariantVote = async (
  variantId: string,
  direction: VoteDirection,
): Promise<void> => {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('login required to vote')

  const url = `${SUPABASE_URL}/rest/v1/variant_votes?on_conflict=variant_id,user_id`
  const res = await fetchWithTimeout(url, {
    method: 'POST',
    headers: {
      ...restHeaders(token),
      'Content-Type': 'application/json',
      Prefer: 'resolution=merge-duplicates,return=minimal',
    },
    body: JSON.stringify({ variant_id: variantId, value: direction }),
  })
  if (!res.ok) throw new Error(`vote set failed: ${res.status} ${await res.text()}`)
}

export const clearVariantVote = async (variantId: string): Promise<void> => {
  if (!SUPABASE_URL) throw new Error('variants backend not configured')
  const token = await getValidAccessToken()
  const session = getSession()
  if (!token || !session) throw new Error('login required to vote')

  const url = `${SUPABASE_URL}/rest/v1/variant_votes`
    + `?variant_id=eq.${encodeURIComponent(variantId)}`
    + `&user_id=eq.${encodeURIComponent(session.user.id)}`
  const res = await fetchWithTimeout(url, { method: 'DELETE', headers: restHeaders(token) })
  if (!res.ok) throw new Error(`vote remove failed: ${res.status}`)
}

// Returns a Map of variant_id → direction for the current user. Anon → empty.
export const listMyVariantVotes = async (): Promise<Map<string, VoteDirection>> => {
  if (!SUPABASE_URL) return new Map()
  const token = await getValidAccessToken()
  if (!token) return new Map()

  const res = await fetchWithTimeout(
    `${SUPABASE_URL}/rest/v1/variant_votes?select=variant_id,value`,
    { headers: restHeaders(token) },
  )
  if (!res.ok) return new Map()
  const rows = (await res.json()) as Array<{ variant_id: string; value: number }>
  return new Map(rows.map(r => [r.variant_id, (r.value === -1 ? -1 : 1) as VoteDirection]))
}

// Returns the set of variant_ids the current user has contributed to. Drives
// the "this is one of mine" badge + the disable-vote rule on own variants.
export const listMyContributions = async (): Promise<Set<string>> => {
  if (!SUPABASE_URL) return new Set()
  const token = await getValidAccessToken()
  const session = getSession()
  if (!token || !session) return new Set()

  const res = await fetchWithTimeout(
    `${SUPABASE_URL}/rest/v1/variant_contributors_read`
      + `?user_id=eq.${encodeURIComponent(session.user.id)}`
      + `&select=variant_id`,
    { headers: restHeaders(token) },
  )
  if (!res.ok) return new Set()
  const rows = (await res.json()) as Array<{ variant_id: string }>
  return new Set(rows.map(r => r.variant_id))
}
