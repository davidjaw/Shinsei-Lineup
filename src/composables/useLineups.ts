import { reactive, ref, computed } from 'vue'
import { Hero, Skill, Trait } from './useData'

// Types
export interface RoleData {
  hero: Hero | null
  skill1: Skill | null
  skill2: Skill | null
  stats: {
    lea: number
    val: number
    int: number
    pol: number
    cha: number
    spd: number
  }
  equipTraits: (Trait | null)[]
}

export interface Lineup {
  name: string
  main: RoleData
  vice1: RoleData
  vice2: RoleData
}

// State
const defaultStats = { lea: 100, val: 100, int: 100, pol: 100, cha: 100, spd: 100 }

const emptyRole = (): RoleData => ({
  hero: null,
  skill1: null,
  skill2: null,
  stats: { ...defaultStats },
  equipTraits: [null, null, null, null]
})

const lineups = reactive<Lineup[]>(Array.from({ length: 5 }, (_, i) => ({
  name: `隊伍 ${i + 1}`,
  main: emptyRole(),
  vice1: emptyRole(),
  vice2: emptyRole()
})))

const currentTeamIndex = ref(0)

// Getters
const currentLineup = computed(() => lineups[currentTeamIndex.value])

const currentTeamName = computed({
  get: () => currentLineup.value.name,
  set: (val) => { currentLineup.value.name = val }
})

const allUsedHeroNames = computed(() => {
  const names = new Set<string>()
  lineups.forEach((team) => {
    if (team.main.hero) names.add(team.main.hero.name)
    if (team.vice1.hero) names.add(team.vice1.hero.name)
    if (team.vice2.hero) names.add(team.vice2.hero.name)
  })
  return names
})

const allUsedSkillNames = computed(() => {
  const names = new Set<string>()
  lineups.forEach(team => {
    [team.main, team.vice1, team.vice2].forEach(r => {
      if (r.skill1) names.add(r.skill1.name)
      if (r.skill2) names.add(r.skill2.name)
    })
  })
  return names
})

const totalCost = computed(() => {
  let cost = 0
  const l = currentLineup.value
  if (l.main.hero) cost += l.main.hero.cost
  if (l.vice1.hero) cost += l.vice1.hero.cost
  if (l.vice2.hero) cost += l.vice2.hero.cost
  return cost
})

// Actions
const swapRoles = (roleA: 'main' | 'vice1' | 'vice2', roleB: 'main' | 'vice1' | 'vice2') => {
  if (roleA === roleB) return
  const l = currentLineup.value
  const temp = { ...l[roleA], stats: { ...l[roleA].stats }, equipTraits: [...l[roleA].equipTraits] }
  l[roleA] = { ...l[roleB], stats: { ...l[roleB].stats }, equipTraits: [...l[roleB].equipTraits] }
  l[roleB] = temp
}

const clearLineup = (type: 'all' | 'current') => {
  if (type === 'current') {
    currentLineup.value.main = emptyRole()
    currentLineup.value.vice1 = emptyRole()
    currentLineup.value.vice2 = emptyRole()
  }
  if (type === 'all') {
    lineups.forEach(l => {
      l.main = emptyRole()
      l.vice1 = emptyRole()
      l.vice2 = emptyRole()
    })
  }
}

export function useLineups() {
  return {
    lineups,
    currentTeamIndex,
    currentLineup,
    currentTeamName,
    allUsedHeroNames,
    allUsedSkillNames,
    totalCost,
    emptyRole,
    clearLineup,
    swapRoles
  }
}
