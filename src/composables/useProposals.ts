// Personal-collection state for the 我的提案 surface.
//
// The public feed and voting now live in `useVariants` (canonical hash-based
// model). This composable retains only the my-drafts surface: list / create
// / toggle public/private. Toggling public/private fans out to submit_variant
// / withdraw_variant so the variant pool stays in sync with proposal state.
//
// Functions removed in the variant-first migration:
//   - publicProposals / refreshPublic / loadMorePublic  → use useVariants
//   - vote / myVotes / applyVoteDeltas                  → variants are voted
//
// LineupBuilder consumes only createFromLineup; ProposalsView consumes
// myProposals / loadingMine / refreshMine / togglePublic / remove.

import { ref } from 'vue'
import type { Proposal } from '../types/group'
import type { Lineup } from './useLineups'
import { snapshotTeam } from '../lib/lineup'
import {
  createProposal as remoteCreate,
  updateProposal as remoteUpdate,
  deleteProposal as remoteDelete,
  listMyProposals,
  isProposalsEnabled,
} from '../lib/proposals'
import {
  submitVariant,
  withdrawVariant,
  findVariantForTeam,
} from '../lib/variants'
import { capAuthorName, capTeamName } from '../lib/displayName'
import { useVariants } from './useVariants'

const myProposals = ref<Proposal[]>([])
const loadingMine = ref(false)
const lastError = ref<string | null>(null)

export function useProposals() {
  const { invalidateContributors } = useVariants()

  const refreshMine = async (): Promise<void> => {
    if (!isProposalsEnabled()) return
    loadingMine.value = true
    lastError.value = null
    try {
      myProposals.value = await listMyProposals()
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingMine.value = false
    }
  }

  const createFromLineup = async (
    lineup: Lineup,
    opts: { name: string; isPublic: boolean; authorName?: string | null; forkedFrom?: string | null },
  ): Promise<Proposal> => {
    const team = snapshotTeam(lineup)
    // Centralize the 30-char display-name cap here so every create path gets
    // the same stored author_name without callers having to remember.
    const authorName = capAuthorName(opts.authorName)
    const created = await remoteCreate({ ...opts, authorName, team })
    if (opts.isPublic) {
      try {
        const result = await submitVariant(team, authorName, capTeamName(opts.name))
        invalidateContributors(result.variantId)
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.includes('account banned') || msg.includes('已被封鎖')) throw e
        console.warn('submitVariant during create failed:', e)
      }
    }
    myProposals.value = [created, ...myProposals.value]
    return created
  }

  // Toggling visibility keeps the variant pool in sync: public → submit
  // (idempotent), private → withdraw if a matching variant exists. Variant
  // sync errors are non-fatal; the proposal flip already succeeded.
  const togglePublic = async (id: string, isPublic: boolean): Promise<void> => {
    const updated = await remoteUpdate(id, { isPublic })
    const idx = myProposals.value.findIndex(p => p.id === id)
    if (idx >= 0) myProposals.value[idx] = updated
    try {
      if (isPublic) {
        const result = await submitVariant(
          updated.team,
          capAuthorName(updated.authorName),
          capTeamName(updated.name),
        )
        invalidateContributors(result.variantId)
      } else {
        const variantId = await findVariantForTeam(updated.team)
        if (variantId) {
          await withdrawVariant(variantId)
          invalidateContributors(variantId)
        }
      }
    } catch (e) {
      console.warn('variant sync on togglePublic failed:', e)
    }
  }

  // Delete a proposal. If it was public, withdraw the matching variant first
  // so the public pool doesn't keep a now-orphaned entry. Variant-sync errors
  // are non-fatal; the proposal delete is the user's intent and must proceed.
  const remove = async (id: string): Promise<void> => {
    const target = myProposals.value.find(p => p.id === id)
    if (target?.isPublic) {
      try {
        const variantId = await findVariantForTeam(target.team)
        if (variantId) {
          await withdrawVariant(variantId)
          invalidateContributors(variantId)
        }
      } catch (e) {
        console.warn('variant sync on remove failed:', e)
      }
    }
    await remoteDelete(id)
    myProposals.value = myProposals.value.filter(p => p.id !== id)
  }

  return {
    myProposals,
    loadingMine,
    lastError,
    refreshMine,
    createFromLineup,
    togglePublic,
    remove,
    isEnabled: isProposalsEnabled,
  }
}
