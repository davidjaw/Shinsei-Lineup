// Finding a catalog entry by CHT name, JP key or alias. A leaf: lib/variants.ts reaches
// this through storedTeam.ts while useInventory is loading, so importing useGroups or
// useLineups from here would hit useInventory before it initializes.

import type { Hero, Skill } from '../composables/useData'

// Lookup maps memoized by the input array. Restore visits ~36 keys per group
// (4 teams × 3 roles × 3 fields); building a Map once is O(1) per lookup vs
// O(n) Array.find each time. WeakMap keeps the cache alive only as long as
// the heroes/skills array reference.
const heroLookupCache = new WeakMap<Hero[], Map<string, Hero>>()
const skillLookupCache = new WeakMap<Skill[], Map<string, Skill>>()

const buildLookup = <T extends { name: string; name_jp?: string | null; aliases?: string[] }>(
  items: T[],
): Map<string, T> => {
  const map = new Map<string, T>()
  for (const it of items) {
    if (it.name) map.set(it.name, it)
    if (it.name_jp) map.set(it.name_jp, it)
    if (it.aliases) for (const a of it.aliases) map.set(a, it)
  }
  return map
}

const getHeroLookup = (heroes: Hero[]): Map<string, Hero> => {
  let map = heroLookupCache.get(heroes)
  if (!map) {
    map = buildLookup(heroes)
    heroLookupCache.set(heroes, map)
  }
  return map
}

const getSkillLookup = (skills: Skill[]): Map<string, Skill> => {
  let map = skillLookupCache.get(skills)
  if (!map) {
    map = buildLookup(skills)
    skillLookupCache.set(skills, map)
  }
  return map
}

export const findHeroByKey = (heroes: Hero[], key: string): Hero | undefined =>
  getHeroLookup(heroes).get(key)

export const findSkillByKey = (skills: Skill[], key: string): Skill | undefined =>
  getSkillLookup(skills).get(key)
