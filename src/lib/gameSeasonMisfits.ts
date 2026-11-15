// What a picked game season offers (./gameSeason.ts) and what on a group's teams it does not. The libraries list
// only what is offered; the lineup page marks the misfits where they stand, counts them, and can clear them. Pure:
// the catalog and the teams in, nothing stored. The catalog itself is never narrowed, so saves, shares, cloud rows
// and the inventory still resolve every name.
import type { Hero, Skill } from '../composables/useData'
import type { Lineup } from '../composables/useLineups'
import { gameSeasonOffered, gameSeasonsOf, type HeroRow, type SkillRow } from './gameSeason'
import { clearHeroSlot } from './lineup'

export type GameSeasonRole = 'main' | 'vice1' | 'vice2'
const ROLES: readonly GameSeasonRole[] = ['main', 'vice1', 'vice2']
const SKILL_SLOTS = [1, 2] as const
type SkillSlot = typeof SKILL_SLOTS[number]

/** Which heroes and skills a season offers. */
export interface GameSeasonOffer {
  gameSeason: string
  hero: (hero: HeroRow) => boolean
  skill: (skill: SkillRow) => boolean
}

export function gameSeasonOffer(gameSeason: string, heroes: readonly Hero[]): GameSeasonOffer {
  const of = gameSeasonsOf(heroes)
  return {
    gameSeason,
    hero: (h) => gameSeasonOffered(of.hero(h), gameSeason),
    skill: (s) => gameSeasonOffered(of.skill(s), gameSeason),
  }
}

/** The heroes / skills an offer makes available; no offer, all of them. */
export const offeredHeroes = (heroes: readonly Hero[], offer: GameSeasonOffer | null): Hero[] =>
  offer ? heroes.filter(offer.hero) : [...heroes]
export const offeredSkills = (skills: readonly Skill[], offer: GameSeasonOffer | null): Skill[] =>
  offer ? skills.filter(offer.skill) : [...skills]

export interface GameSeasonMisfit {
  /** The team's place in the group. */
  team: number
  role: GameSeasonRole
  /** null: the hero; 1 or 2: a learned skill. */
  slot: SkillSlot | null
  name: string
}

const skillAt = (team: Lineup, role: GameSeasonRole, slot: SkillSlot): Skill | null =>
  slot === 1 ? team[role].skill1 : team[role].skill2

function roleMisfits(team: Lineup, index: number, role: GameSeasonRole, offer: GameSeasonOffer): GameSeasonMisfit[] {
  const hero = team[role].hero
  const out: GameSeasonMisfit[] = hero && !offer.hero(hero) ? [{ team: index, role, slot: null, name: hero.name }] : []
  for (const slot of SKILL_SLOTS) {
    const skill = skillAt(team, role, slot)
    if (skill && !offer.skill(skill)) out.push({ team: index, role, slot, name: skill.name })
  }
  return out
}

/** The heroes and learned skills on `teams` the offer leaves out, team by team, a hero before its skills. */
export const gameSeasonMisfits = (teams: readonly Lineup[], offer: GameSeasonOffer): GameSeasonMisfit[] =>
  teams.flatMap((team, i) => ROLES.flatMap((role) => roleMisfits(team, i, role, offer)))

function clearMisfit(teams: Lineup[], m: GameSeasonMisfit): void {
  const role = teams[m.team]?.[m.role]
  if (!role) return
  if (m.slot === null) {
    if (role.hero?.name === m.name) clearHeroSlot(role)
    return
  }
  if (skillAt(teams[m.team], m.role, m.slot)?.name !== m.name) return
  if (m.slot === 1) role.skill1 = null
  else role.skill2 = null
}

/** Clears the misfits from `teams`: a hero clears its whole slot, a skill only itself. A slot that changed since the
 *  list was made (another name there now) is left alone. */
export function clearGameSeasonMisfits(teams: Lineup[], misfits: readonly GameSeasonMisfit[]): void {
  for (const m of misfits) clearMisfit(teams, m)
}

/** How one slot is marked: whether its hero is off-season, and which of its learned skills are. */
export interface GameSeasonSlotMark {
  hero: boolean
  skills: SkillSlot[]
}

/** The marks of one team's slots, from the group's misfits; a slot with nothing off-season is absent. */
export function gameSeasonSlotMarks(misfits: readonly GameSeasonMisfit[], team: number): Partial<Record<GameSeasonRole, GameSeasonSlotMark>> {
  const marks: Partial<Record<GameSeasonRole, GameSeasonSlotMark>> = {}
  for (const m of misfits.filter((x) => x.team === team)) {
    const mark = (marks[m.role] ??= { hero: false, skills: [] })
    if (m.slot === null) mark.hero = true
    else mark.skills.push(m.slot)
  }
  return marks
}

/** The distinct names of a misfit list, in order: what the dialogs list. */
export const gameSeasonMisfitNames = (misfits: readonly GameSeasonMisfit[]): string[] =>
  [...new Set(misfits.map((m) => m.name))]
