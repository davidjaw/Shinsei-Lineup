import { reactive, ref, computed } from 'vue'
import { Hero, Skill, Trait, BingxueDirection } from './useData'

// Active 兵學 selection for a hero. A hero activates ONE direction at a time,
// picks 1 of 3 majors (1 pt), plus minors from 6 available using a 5-point budget.
// Each minor costs `level` points (Lv1=1pt, Lv2=2pt). Total of .minors.level sums
// must be ≤5. `direction: null` = 兵學 not yet configured.
export interface BingxueMinor {
  name: string          // JP key
  level: 1 | 2
}

export interface BingxueActive {
  direction: BingxueDirection | null
  major: string | null
  minors: BingxueMinor[]
}

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
  breakthrough: number  // 0-5, controls which traits are active
  bingxue: BingxueActive
}

export interface Lineup {
  name: string
  main: RoleData
  vice1: RoleData
  vice2: RoleData
}

// State
const defaultStats = { lea: 100, val: 100, int: 100, pol: 100, cha: 100, spd: 100 }

const emptyBingxue = (): BingxueActive => ({
  direction: null,
  major: null,
  minors: [],
})

const emptyRole = (): RoleData => ({
  hero: null,
  skill1: null,
  skill2: null,
  stats: { ...defaultStats },
  equipTraits: [null, null, null, null],
  breakthrough: 0,
  bingxue: emptyBingxue(),
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
  const clone = (r: RoleData): RoleData => ({
    ...r,
    stats: { ...r.stats },
    equipTraits: [...r.equipTraits],
    bingxue: { ...r.bingxue, minors: r.bingxue.minors.map(m => ({ ...m })) },
  })
  const temp = clone(l[roleA])
  l[roleA] = clone(l[roleB])
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
