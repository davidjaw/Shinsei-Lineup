// Lineup-shape utility helpers shared across composables and components.
// Kept dependency-free (no Vue, no Supabase) so it can be imported anywhere
// without ordering hazards.

import type { Lineup, RoleData } from '../composables/useLineups'

/** Clear a slot the way its ✕ button does (LineupSlot.removeHero): the hero with its 戰法, 突破 and 兵學. */
export const clearHeroSlot = (role: RoleData): void => {
  role.hero = null
  role.skill1 = null
  role.skill2 = null
  role.breakthrough = 0
  role.bingxue = { direction: null, major: null, minors: [] }
}

/** Deep-clone a Lineup so callers can mutate the snapshot without aliasing
 *  reactive state (or the immutable team_blob coming back from Supabase).
 *  Uses JSON round-trip — fine for our blob shape (plain data, no Date /
 *  Map / Set fields), and consistent with how the existing
 *  ExportTeamToGroupDialog import path clones. */
export const snapshotTeam = (lineup: Lineup): Lineup =>
  JSON.parse(JSON.stringify(lineup)) as Lineup

/** Return the Lineup with vice1/vice2 swapped if needed so vice hero names
 *  appear in canonical (alphabetical) order. The variant hash already
 *  collapses vice positions; this ensures display order matches across
 *  every surface that renders the same logical variant, so column rhythm
 *  is stable from drawer header → sidebar → variant card.
 *
 *  The swap is structural (vice slots carry their full skill/兵學 bundle),
 *  not just name-level — same comparator as the server-side hash function
 *  to keep client + server in lockstep. */
export const withCanonicalViceOrder = (team: Lineup): Lineup => {
  const v1 = team.vice1.hero?.name ?? ''
  const v2 = team.vice2.hero?.name ?? ''
  if (v1 <= v2) return team
  return { ...team, vice1: team.vice2, vice2: team.vice1 }
}

/** The sorted (vice1, vice2) heroes for display surfaces that need the
 *  heroes alone without the rest of the lineup blob (e.g., the sidebar
 *  list, the variant drawer header). Returns null in slots without a hero
 *  so callers can render a placeholder uniformly. */
export const sortedViceHeroes = (team: Lineup | null | undefined) => {
  if (!team) return [null, null] as const
  const v1 = team.vice1?.hero ?? null
  const v2 = team.vice2?.hero ?? null
  const n1 = v1?.name ?? ''
  const n2 = v2?.name ?? ''
  return n1 <= n2 ? [v1, v2] as const : [v2, v1] as const
}
