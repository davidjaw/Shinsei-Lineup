import type { Hero, Skill } from '../composables/useData'
import type { HandbookSnapshot } from './handbookSialia'

export type { HandbookSnapshot }
export { parseSnapshotId, SNAPSHOT_ID_RE } from './handbookSialia'

export interface MappedHandbookInventory {
  chtHeroes: string[]
  chtSkills: string[]
  inv_h: string[]
  inv_s: string[]
  unmatchedHeroes: number[]
  unmatchedSkills: number[]
}

const jpKey = (name: string, nameJp?: string | null): string =>
  nameJp || name

export function mapHandbookInventory(
  snap: HandbookSnapshot,
  heroes: Hero[],
  skills: Skill[],
): MappedHandbookInventory {
  const heroByCfg = new Map<number, Hero>()
  for (const h of heroes) {
    if (h.cfg_id != null) heroByCfg.set(h.cfg_id, h)
  }
  const skillByCfg = new Map<number, Skill>()
  for (const s of skills) {
    if (s.cfg_id != null) skillByCfg.set(s.cfg_id, s)
  }

  const chtHeroes: string[] = []
  const inv_h: string[] = []
  const unmatchedHeroes: number[] = []
  const seenHero = new Set<string>()
  for (const id of snap.hero_ids) {
    const hero = heroByCfg.get(id)
    if (!hero) {
      unmatchedHeroes.push(id)
      continue
    }
    if (seenHero.has(hero.name)) continue
    seenHero.add(hero.name)
    chtHeroes.push(hero.name)
    inv_h.push(jpKey(hero.name, hero.name_jp))
  }

  const chtSkills: string[] = []
  const inv_s: string[] = []
  const unmatchedSkills: number[] = []
  const seenSkill = new Set<string>()
  for (const id of snap.skill_ids) {
    const skill = skillByCfg.get(id)
    if (!skill) {
      unmatchedSkills.push(id)
      continue
    }
    if (seenSkill.has(skill.name)) continue
    seenSkill.add(skill.name)
    chtSkills.push(skill.name)
    inv_s.push(jpKey(skill.name, skill.name_jp))
  }

  return { chtHeroes, chtSkills, inv_h, inv_s, unmatchedHeroes, unmatchedSkills }
}
