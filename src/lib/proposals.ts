// Supabase REST client for the proposal (= personal-collection 精選隊伍)
// surface. The public feed + voting moved to `variants.ts` in the
// variant-first migration; this file now covers only my-drafts CRUD.
//
// Public proposals stay readable via RLS for the legacy direct-link flow,
// but the public listing endpoint (listPublicProposals) is gone — the
// variant feed replaced it.

import { SUPABASE_URL, fetchWithTimeout, isSupabaseConfigured, restHeaders } from './supabase'
import { getSession, getValidAccessToken } from './auth'
import { mapRpcError } from './variants'
import type { Proposal } from '../types/group'

interface ProposalRow {
  id: string
  name: string
  team_blob: unknown
  is_public: boolean
  user_id: string | null
  author_name: string | null
  vote_count: number
  upvote_count: number
  downvote_count: number
  forked_from: string | null
  created_at: string
  updated_at: string
}

const rowToProposal = (row: ProposalRow): Proposal => ({
  id: row.id,
  name: row.name,
  team: row.team_blob as Proposal['team'],
  isPublic: row.is_public,
  authorId: row.user_id,
  authorName: row.author_name,
  voteCount: row.vote_count,
  // Older rows from pre-migration deploys may lack the per-direction columns.
  upvoteCount: row.upvote_count ?? 0,
  downvoteCount: row.downvote_count ?? 0,
  forkedFrom: row.forked_from,
  createdAt: row.created_at,
  updatedAt: row.updated_at,
})

export const isProposalsEnabled = isSupabaseConfigured

export interface CreateProposalInput {
  name: string
  team: Proposal['team']
  isPublic: boolean
  forkedFrom?: string | null
  authorName?: string | null
}

/** Insert a new proposal. Auth required so every submission is attributable. */
export const createProposal = async (input: CreateProposalInput): Promise<Proposal> => {
  if (!SUPABASE_URL) throw new Error('proposals backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('login required to create a proposal')

  // description column is intentionally omitted — the UI no longer accepts
  // user-supplied descriptions (anti-harassment); the DB default is NULL.
  const body = {
    name: input.name,
    team_blob: input.team,
    is_public: input.isPublic,
    forked_from: input.forkedFrom ?? null,
    author_name: input.authorName ?? null,
  }

  const res = await fetchWithTimeout(`${SUPABASE_URL}/rest/v1/proposals`, {
    method: 'POST',
    headers: {
      ...restHeaders(token),
      'Content-Type': 'application/json',
      Prefer: 'return=representation',
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(mapRpcError(body, `proposal create failed: ${res.status} ${body}`))
  }
  const rows = (await res.json()) as ProposalRow[]
  return rowToProposal(rows[0])
}

/** Update a proposal (owner only via RLS). Use for renaming or flipping
 *  is_public after the fact. */
export const updateProposal = async (
  id: string,
  patch: Partial<Pick<CreateProposalInput, 'name' | 'isPublic'>>,
): Promise<Proposal> => {
  if (!SUPABASE_URL) throw new Error('proposals backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('login required to update a proposal')

  const body: Record<string, unknown> = {}
  if (patch.name !== undefined) body.name = patch.name
  if (patch.isPublic !== undefined) body.is_public = patch.isPublic

  const res = await fetchWithTimeout(`${SUPABASE_URL}/rest/v1/proposals?id=eq.${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: {
      ...restHeaders(token),
      'Content-Type': 'application/json',
      Prefer: 'return=representation',
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(mapRpcError(body, `proposal update failed: ${res.status} ${body}`))
  }
  const rows = (await res.json()) as ProposalRow[]
  return rowToProposal(rows[0])
}

/** Delete a proposal (owner only via RLS). */
export const deleteProposal = async (id: string): Promise<void> => {
  if (!SUPABASE_URL) throw new Error('proposals backend not configured')
  const token = await getValidAccessToken()
  if (!token) throw new Error('login required to delete a proposal')

  const res = await fetchWithTimeout(`${SUPABASE_URL}/rest/v1/proposals?id=eq.${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: restHeaders(token),
  })
  if (!res.ok) throw new Error(`proposal delete failed: ${res.status}`)
}

/** List the current user's own proposals (private + public). Auth required.
 *  Must filter by user_id explicitly: the proposals table has an OR of RLS
 *  SELECT policies (owner OR is_public), so an unfiltered query also returns
 *  every public proposal from other users — they would leak into 我的提案. */
export const listMyProposals = async (): Promise<Proposal[]> => {
  if (!SUPABASE_URL) throw new Error('proposals backend not configured')
  const token = await getValidAccessToken()
  if (!token) return []
  const userId = getSession()?.user.id
  if (!userId) return []

  const url = `${SUPABASE_URL}/rest/v1/proposals?select=*&user_id=eq.${encodeURIComponent(userId)}&order=updated_at.desc`
  const res = await fetchWithTimeout(url, { headers: restHeaders(token) })
  if (!res.ok) throw new Error(`proposals list failed: ${res.status}`)
  return ((await res.json()) as ProposalRow[]).map(rowToProposal)
}
