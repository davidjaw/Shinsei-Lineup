// Phase 2 type-layer for the dual-mode lineup model.
//
// Two modes:
//   - 編組 (Group): a set of up to 5 teams sharing a hero/skill uniqueness
//     constraint — mirrors what the user actually owns in the live game.
//   - 精選隊伍 (FeaturedTeam — kept as `Proposal` in code/DB for backwards
//     compatibility): a single team frozen as a snapshot, optionally made
//     public for community sharing/voting/import. No uniqueness constraint
//     vs. anything else (theory-craft). The CHT label was originally
//     "配將提案" but that name is reserved for a future group-level
//     theory-craft suggestion feature.
//
// `Lineup` (= Team) lives in useLineups; we only re-export the alias here so
// upstream consumers can read intent without ambient cross-imports.
import type { Lineup } from '../composables/useLineups'

/** Alias: a Team is one Lineup. Use Team in group/proposal contexts where
 *  "Lineup" reads ambiguously. */
export type Team = Lineup

/**
 * A 編組 holds up to MAX_TEAMS_PER_GROUP teams. Within a group, a hero or
 * skill may appear in at most one team — this enforces the inventory truth
 * that you can't put 黒田官兵衛 in two teams simultaneously when you only own
 * one copy.
 *
 * The 10 limit matches the existing `lineups` array length so all current
 * users fit a single default group on migration without truncation.
 */
export interface Group {
  id: string
  name: string
  teams: Team[]
}

export const MAX_TEAMS_PER_GROUP = 10

/**
 * How to resolve hero/skill collisions when importing a proposal team into
 * a group that already uses the same hero/skill in another team.
 *
 * - 'cancel': abort the import.
 * - 'overwrite': remove the colliding hero/skill from its existing team in
 *   the group, then place the imported team intact.
 * - 'leave-empty': place the imported team but null out any role whose hero
 *   collides; the existing team keeps its hero.
 *
 * Surface in `ExportTeamToGroupDialog` (shared between LineupBuilder's
 * "導出到其他編組" entrypoint and the ProposalsView "匯入到編組" button).
 */
export type ImportConflictResolution = 'cancel' | 'overwrite' | 'leave-empty'

/**
 * A 精選隊伍 (rendered as "FeaturedTeam" in CHT UI labels; type stays
 * `Proposal` for backwards compat with the DB column name) is a snapshot
 * of a single team. Snapshots are intentionally
 * data-redundant (we copy hero/skill names, not just ids) so a future
 * pipeline rename of a hero/skill doesn't retroactively mutate the proposal.
 *
 * `isPublic` defaults false — the share toggle in the create dialog defaults
 * to private and only lifts to public when the user opts in.
 */
export interface Proposal {
  id: string
  /** Free-text label, max ~50 chars (UI-enforced). */
  name: string
  /** Optional short rationale. Legacy: the UI no longer surfaces description
   *  (removed to keep the public feed harassment-free), but the DB column
   *  remains for old rows. New proposals are created with description = null. */
  description?: string
  /** Frozen team payload — same shape as Lineup but with snapshot semantics. */
  team: Team
  /** False = private (only owner sees it); True = public (listed on the proposal feed). */
  isPublic: boolean
  /** Author's user_id from Supabase auth, null for anonymous local-only proposals. */
  authorId: string | null
  /** Author display name at the time of share (frozen). */
  authorName: string | null
  /** Net score (upvoteCount − downvoteCount); used to rank the public feed. */
  voteCount: number
  /** Per-direction counters; denormalized from proposal_votes for cheap reads. */
  upvoteCount: number
  downvoteCount: number
  /** ISO timestamps. */
  createdAt: string
  updatedAt: string
  /** Optional reference to a parent proposal this was forked from. */
  forkedFrom: string | null
}

export const DEFAULT_GROUP_NAME = '預設'
