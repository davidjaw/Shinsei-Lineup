// State + actions for the variant-first 精選隊伍 feature.
//
// Two-level model:
//   - Level 1: HeroSet grid (3-hero combos, no skills)  — `heroSets`
//   - Level 2: Variants under one HeroSet (skills/兵學) — `activeVariants`
//
// All hashing happens server-side. The composable manages: reactive state,
// optimistic voting deltas, contributor cache, sort/filter selections.

import { ref, computed } from 'vue'
import type { Lineup } from './useLineups'
import { snapshotTeam } from '../lib/lineup'
import { getSession } from '../lib/auth'
import {
  listHeroSets,
  listVariantsInSet,
  listContributors,
  submitVariant as remoteSubmit,
  withdrawVariant as remoteWithdraw,
  setVariantVote,
  clearVariantVote,
  listMyVariantVotes,
  listMyContributions,
  isVariantsEnabled,
  reportContent,
  adminSetNameHidden,
  type HeroSetSummary,
  type Variant,
  type VariantContributor,
  type VariantSort,
  type VoteDirection,
  type ReportKind,
} from '../lib/variants'
import { adminListBannedUserIds, adminSetUserBanned } from '../lib/bans'

export type HeroSetSort = 'total' | 'recent' | 'latest' | 'count'

const heroSets = ref<HeroSetSummary[]>([])
const variantsBySet = ref<Map<string, Variant[]>>(new Map())
const contributorsByVariant = ref<Map<string, VariantContributor[]>>(new Map())
const myVotes = ref<Map<string, VoteDirection>>(new Map())
const myContributions = ref<Set<string>>(new Set())
const bannedUserIds = ref<Set<string>>(new Set())

const activeHeroSetHash = ref<string | null>(null)
const heroSetSort = ref<HeroSetSort>('total')
const variantSort = ref<VariantSort>('votes')

const loadingSets = ref(false)
const loadingVariants = ref(false)
const lastError = ref<string | null>(null)

export function useVariants() {

  const refreshHeroSets = async (): Promise<void> => {
    if (!isVariantsEnabled()) return
    loadingSets.value = true
    lastError.value = null
    try {
      heroSets.value = await listHeroSets()
      myVotes.value = await listMyVariantVotes()
      myContributions.value = await listMyContributions()
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingSets.value = false
    }
  }

  const selectHeroSet = async (hash: string | null): Promise<void> => {
    activeHeroSetHash.value = hash
    if (!hash) return
    // Cache hit: skip refetch on re-open. Caller can force via refreshActive.
    if (variantsBySet.value.has(hash)) return
    await refreshActive()
  }

  const refreshActive = async (): Promise<void> => {
    const hash = activeHeroSetHash.value
    if (!hash || !isVariantsEnabled()) return
    loadingVariants.value = true
    try {
      const rows = await listVariantsInSet(hash, variantSort.value)
      const next = new Map(variantsBySet.value)
      next.set(hash, rows)
      variantsBySet.value = next
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingVariants.value = false
    }
  }

  const fetchContributors = async (variantId: string): Promise<VariantContributor[]> => {
    if (contributorsByVariant.value.has(variantId)) {
      return contributorsByVariant.value.get(variantId)!
    }
    const rows = await listContributors(variantId)
    const next = new Map(contributorsByVariant.value)
    next.set(variantId, rows)
    contributorsByVariant.value = next
    return rows
  }

  // Drop cached contributor lists so the next fetch hits the network.
  // Omit variantId to clear the whole cache.
  const invalidateContributors = (variantId?: string): void => {
    if (!variantId) {
      contributorsByVariant.value = new Map()
      return
    }
    if (!contributorsByVariant.value.has(variantId)) return
    const next = new Map(contributorsByVariant.value)
    next.delete(variantId)
    contributorsByVariant.value = next
  }

  // Active variants for the open HeroSet, sorted client-side. Server already
  // sorts by votes; resort here when the user flips between votes/latest
  // without a network round-trip.
  const activeVariants = computed<Variant[]>(() => {
    const hash = activeHeroSetHash.value
    if (!hash) return []
    const rows = variantsBySet.value.get(hash) ?? []
    if (variantSort.value === 'votes') {
      return [...rows].sort((a, b) => b.voteCount - a.voteCount
        || (a.updatedAt < b.updatedAt ? 1 : -1))
    }
    return [...rows].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
  })

  const activeHeroSet = computed<HeroSetSummary | null>(() => {
    const hash = activeHeroSetHash.value
    if (!hash) return null
    return heroSets.value.find(s => s.heroSetHash === hash) ?? null
  })

  // Apply HeroSet-level sort.
  const sortedHeroSets = computed<HeroSetSummary[]>(() => {
    const rows = [...heroSets.value]
    switch (heroSetSort.value) {
      case 'recent':
        return rows.sort((a, b) => b.recentVoteDelta - a.recentVoteDelta
          || b.totalVoteCount - a.totalVoteCount)
      case 'latest':
        return rows.sort((a, b) => (a.lastActiveAt < b.lastActiveAt ? 1 : -1))
      case 'count':
        return rows.sort((a, b) => b.variantCount - a.variantCount
          || b.totalVoteCount - a.totalVoteCount)
      case 'total':
      default:
        return rows.sort((a, b) => b.totalVoteCount - a.totalVoteCount
          || (a.lastActiveAt < b.lastActiveAt ? 1 : -1))
    }
  })

  // Optimistic vote-count maintenance, mirroring the proposal_votes pattern.
  // Centralised here so callers don't reinvent the four-case arithmetic.
  const applyVoteDeltas = (
    id: string,
    prev: VoteDirection | undefined,
    next: VoteDirection | undefined,
  ): void => {
    let dUp = 0, dDown = 0, dNet = 0
    if (prev === 1)  { dUp--;   dNet-- }
    if (prev === -1) { dDown--; dNet++ }
    if (next === 1)  { dUp++;   dNet++ }
    if (next === -1) { dDown++; dNet-- }
    const variantsNext = new Map(variantsBySet.value)
    for (const [hash, list] of variantsNext) {
      variantsNext.set(hash, list.map(v => v.id === id
        ? {
            ...v,
            upvoteCount:   Math.max(0, v.upvoteCount   + dUp),
            downvoteCount: Math.max(0, v.downvoteCount + dDown),
            voteCount:     v.voteCount + dNet,
          }
        : v,
      ))
    }
    variantsBySet.value = variantsNext
  }

  const vote = async (variantId: string, direction: VoteDirection): Promise<void> => {
    const prev = myVotes.value.get(variantId)
    const next: VoteDirection | undefined = prev === direction ? undefined : direction

    const prevVotes = myVotes.value
    const prevVariants = variantsBySet.value

    const nextMap = new Map(prevVotes)
    if (next === undefined) nextMap.delete(variantId)
    else nextMap.set(variantId, next)
    myVotes.value = nextMap
    applyVoteDeltas(variantId, prev, next)

    try {
      if (next === undefined) await clearVariantVote(variantId)
      else await setVariantVote(variantId, next)
    } catch (e) {
      myVotes.value = prevVotes
      variantsBySet.value = prevVariants
      throw e
    }
  }

  const submitFromLineup = async (
    lineup: Lineup,
    authorName: string | null,
    teamName?: string | null,
  ): Promise<{ variantId: string; isNew: boolean; heroSetHash: string }> => {
    const team = snapshotTeam(lineup)
    const result = await remoteSubmit(team, authorName, teamName)
    // Mark as own contribution so the vote-restriction kicks in immediately.
    myContributions.value = new Set([...myContributions.value, result.variantId])
    invalidateContributors(result.variantId)
    // Cheapest correct refresh: invalidate the affected HeroSet so the next
    // open sees the new variant (or new contributor on the existing one).
    const variantsNext = new Map(variantsBySet.value)
    variantsNext.delete(result.heroSetHash)
    variantsBySet.value = variantsNext
    // Refresh the Level-1 grid so the new HeroSet (or the bumped stats on an
    // existing one) is visible without a manual reload.
    void refreshHeroSets()
    return result
  }

  const withdraw = async (variantId: string): Promise<{ deleted: boolean }> => {
    const result = await remoteWithdraw(variantId)
    const nextContributions = new Set(myContributions.value)
    nextContributions.delete(variantId)
    myContributions.value = nextContributions

    if (result.deleted) {
      // Strip the deleted variant from any cached HeroSet list. The
      // variant_contributors rows for it are cascade-deleted in DB; mirror
      // that by dropping the local cache entry too.
      const variantsNext = new Map(variantsBySet.value)
      for (const [hash, list] of variantsNext) {
        const filtered = list.filter(v => v.id !== variantId)
        if (filtered.length !== list.length) variantsNext.set(hash, filtered)
      }
      variantsBySet.value = variantsNext
      const contribNext = new Map(contributorsByVariant.value)
      contribNext.delete(variantId)
      contributorsByVariant.value = contribNext
    } else {
      // Caller withdrew but other contributors remain — surgically remove
      // the caller's own row from the cached contributor list so the +N
      // chip and tooltip don't show the stale count until next refresh.
      const session = getSession()
      const cached = contributorsByVariant.value.get(variantId)
      if (session && cached) {
        const filtered = cached.filter(c => c.userId !== session.user.id)
        if (filtered.length !== cached.length) {
          const contribNext = new Map(contributorsByVariant.value)
          contribNext.set(variantId, filtered)
          contributorsByVariant.value = contribNext
        }
      }
    }

    void refreshHeroSets()
    return { deleted: result.deleted }
  }

  const report = async (
    kind: ReportKind,
    variantId: string | null,
    targetUserId: string,
  ): Promise<{ ok: true; hidden: boolean; alreadyReported: boolean }> => {
    const result = await reportContent({ kind, variantId, targetUserId })
    if (result.hidden) {
      const next = new Map(contributorsByVariant.value)
      if (kind === 'team_name' && variantId) {
        const rows = next.get(variantId)
        if (rows) {
          next.set(variantId, rows.map(c =>
            c.userId === targetUserId ? { ...c, teamNameHidden: true } : c,
          ))
        }
      } else if (kind === 'display_name') {
        for (const [id, rows] of next) {
          next.set(id, rows.map(c =>
            c.userId === targetUserId ? { ...c, authorNameHidden: true } : c,
          ))
        }
      }
      contributorsByVariant.value = next
    }
    return result
  }

  const setNameHidden = async (
    kind: ReportKind,
    variantId: string | null,
    targetUserId: string,
    hidden: boolean,
    locked = false,
  ): Promise<{ ok: true; hidden: boolean; locked: boolean }> => {
    const result = await adminSetNameHidden({ kind, variantId, targetUserId, hidden, locked })
    const next = new Map(contributorsByVariant.value)
    if (kind === 'team_name' && variantId) {
      const rows = next.get(variantId)
      if (rows) {
        next.set(variantId, rows.map(c =>
          c.userId === targetUserId
            ? { ...c, teamNameHidden: result.hidden, teamNameLocked: result.locked }
            : c,
        ))
      }
    } else if (kind === 'display_name') {
      for (const [id, rows] of next) {
        next.set(id, rows.map(c =>
          c.userId === targetUserId
            ? { ...c, authorNameHidden: result.hidden, authorNameLocked: result.locked }
            : c,
        ))
      }
    }
    contributorsByVariant.value = next
    // Unlock/unhide: GET had nulled locked names, so refetch to restore them.
    if (!result.hidden) {
      if (kind === 'team_name' && variantId) {
        invalidateContributors(variantId)
        await fetchContributors(variantId)
      } else if (kind === 'display_name') {
        const ids = [...contributorsByVariant.value.keys()]
        invalidateContributors()
        await Promise.all(ids.map(id => fetchContributors(id)))
      }
    }
    return result
  }

  const refreshBannedUsers = async (): Promise<void> => {
    try {
      bannedUserIds.value = new Set(await adminListBannedUserIds())
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e)
    }
  }

  const setUserBanned = async (
    userId: string,
    banned: boolean,
  ): Promise<{ ok: true; banned: boolean }> => {
    const result = await adminSetUserBanned({ userId, banned })
    const next = new Set(bannedUserIds.value)
    if (result.banned) next.add(userId)
    else next.delete(userId)
    bannedUserIds.value = next
    return result
  }

  return {
    // state
    heroSets,
    sortedHeroSets,
    activeHeroSetHash,
    activeHeroSet,
    activeVariants,
    contributorsByVariant,
    myVotes,
    myContributions,
    bannedUserIds,
    heroSetSort,
    variantSort,
    loadingSets,
    loadingVariants,
    lastError,
    // actions
    refreshHeroSets,
    refreshActive,
    selectHeroSet,
    fetchContributors,
    invalidateContributors,
    vote,
    submitFromLineup,
    withdraw,
    report,
    setNameHidden,
    refreshBannedUsers,
    setUserBanned,
    isEnabled: isVariantsEnabled,
  }
}
