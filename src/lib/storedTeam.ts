// Reading a team as proposals and variants store it: a frozen Lineup from
// whichever client wrote it. The new site's blobs carry no art, so what a stored
// hero or skill lacks comes from this catalog, by name. What it holds stays:
// the server hashes these names when the team is handed back, and the name is
// the row's identity even if the catalog has since renamed it.

import { toRaw } from 'vue'
import { useData, type Hero, type Skill } from '../composables/useData'
import type { Lineup } from '../composables/useLineups'
import { findHeroByKey, findSkillByKey } from './catalogLookup'

export interface StoredTeamCatalog {
  heroes: Hero[]
  skills: Skill[]
}

const fill = <T extends object>(stored: T, live: T | undefined): T => {
  if (!live) return stored
  const held = Object.entries(stored).filter(([, value]) => value != null && value !== '')
  return { ...live, ...Object.fromEntries(held) }
}

export const fillStoredTeam = (raw: unknown, { heroes, skills }: StoredTeamCatalog): Lineup => {
  const team = raw as Lineup
  if (!team) return team
  const filled = { ...team }
  for (const key of ['main', 'vice1', 'vice2'] as const) {
    const role = team[key]
    if (!role) continue
    filled[key] = {
      ...role,
      hero: role.hero && fill(role.hero, findHeroByKey(heroes, role.hero.name)),
      skill1: role.skill1 && fill(role.skill1, findSkillByKey(skills, role.skill1.name)),
      skill2: role.skill2 && fill(role.skill2, findSkillByKey(skills, role.skill2.name)),
    }
  }
  return filled
}

export const readStoredTeam = (raw: unknown): Lineup => {
  const { heroes, skills } = useData()
  return fillStoredTeam(raw, { heroes: toRaw(heroes.value), skills: toRaw(skills.value) })
}
