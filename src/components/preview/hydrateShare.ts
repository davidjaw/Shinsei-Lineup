// Pure hydration of a stored ShareableData blob into Lineup objects suitable
// for feeding TeamPreviewCard / GroupPreviewCard. Mirrors LineupBuilder's
// restoreFromBlob but produces fresh objects instead of mutating in place —
// the preview is read-only and must not perturb the active group.

import type { ShareableData, ShareableLineup } from '../../constants/gameData'
import { shareableGroupsInBlob } from '../../lib/lineupSerialize'
import type { Hero, Skill } from '../../composables/useData'
import type { Lineup, RoleData } from '../../composables/useLineups'
import { makeTeam } from '../../composables/useLineups'

export interface HydrateInputs {
  heroes: Hero[]
  skills: Skill[]
}

const findHeroByKey = (heroes: Hero[], key: string): Hero | undefined =>
  heroes.find(h => h.name_jp === key || h.name === key || h.aliases?.includes(key))

const findSkillByKey = (skills: Skill[], key: string): Skill | undefined =>
  skills.find(s => s.name_jp === key || s.name === key || s.aliases?.includes(key))

const restoreRole = (
  prefix: string,
  role: RoleData,
  l: ShareableLineup,
  inputs: HydrateInputs,
): void => {
  const safeL = l as unknown as Record<string, unknown>
  const hName = safeL[prefix] as string | undefined
  if (hName) role.hero = findHeroByKey(inputs.heroes, hName) ?? null
  const s1Name = safeL[`${prefix}_s1`] as string | undefined
  if (s1Name) role.skill1 = findSkillByKey(inputs.skills, s1Name) ?? null
  const s2Name = safeL[`${prefix}_s2`] as string | undefined
  if (s2Name) role.skill2 = findSkillByKey(inputs.skills, s2Name) ?? null
  const bt = safeL[`${prefix}_bt`]
  if (typeof bt === 'number') role.breakthrough = Math.max(0, Math.min(5, bt))
  const bx = safeL[`${prefix}_bx`] as { d?: string; m?: string; n?: { n: string; l: number }[] } | undefined
  if (bx?.d) {
    role.bingxue = {
      direction: bx.d as RoleData['bingxue']['direction'],
      major: bx.m ?? null,
      minors: Array.isArray(bx.n) ? bx.n.map(mi => ({ name: mi.n, level: mi.l as 1 | 2 })) : [],
    }
  }
}

const hydrateTeam = (l: ShareableLineup, idx: number, inputs: HydrateInputs): Lineup => {
  const team = makeTeam(idx)
  if (l.name) team.name = l.name
  restoreRole('m', team.main, l, inputs)
  restoreRole('v1', team.vice1, l, inputs)
  restoreRole('v2', team.vice2, l, inputs)
  return team
}

export interface HydratedShare {
  /** Single team — present for v2 single-team and v1 shares. */
  team?: Lineup
  /** Multi-team group — present for v3 groups envelope or v2 with multiple lineups. */
  group?: { name: string; teams: Lineup[] }
}

export const hydrateShare = (data: ShareableData, inputs: HydrateInputs): HydratedShare => {
  const envelope = shareableGroupsInBlob(data)
  if (envelope.length > 0) {
    const g = envelope[0]
    const teams = (g.teams ?? []).map((l, i) => hydrateTeam(l, i, inputs))
    return { group: { name: g.name || '預設', teams } }
  }
  if (data.lineups && data.lineups.length > 0) {
    const teams = data.lineups.map((l, i) => hydrateTeam(l, i, inputs))
    if (teams.length === 1) return { team: teams[0] }
    return { group: { name: '分享編組', teams } }
  }
  return {}
}
