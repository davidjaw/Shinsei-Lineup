import { reactive, computed, watch } from 'vue'
import { Hero, Skill, BingxueDirection } from './useData'
import { useGroups } from './useGroups'
import { useInventory } from './useInventory'
import { MAX_TEAMS_PER_GROUP } from '../types/group'

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
export const defaultStats = { lea: 100, val: 100, int: 100, pol: 100, cha: 100, spd: 100 }

const emptyBingxue = (): BingxueActive => ({
  direction: null,
  major: null,
  minors: [],
})

export const emptyRole = (): RoleData => ({
  hero: null,
  skill1: null,
  skill2: null,
  stats: { ...defaultStats },
  breakthrough: 0,
  bingxue: emptyBingxue(),
})

export const makeTeam = (idx: number): Lineup => ({
  name: `隊伍 ${idx + 1}`,
  main: emptyRole(),
  vice1: emptyRole(),
  vice2: emptyRole(),
})

// A team is "empty" when none of its three roles has a hero assigned —
// skills, breakthrough, and bingxue are meaningless without a hero anchor.
// Used by preview surfaces to hide unused team slots from screencaps.
export const isEmptyTeam = (t: Lineup): boolean =>
  !t.main.hero && !t.vice1.hero && !t.vice2.hero

const { currentGroup, currentTeamIndex, forEachGroup, normalizeWorkspace } = useGroups()
const { catalogMode } = useInventory()

// Phase 3d: groups owns teams; useLineups exposes a stable `lineups` mirror
// of the active group's teams. `splice` keeps the same array proxy across
// group switches so consumers that captured `lineups` once at module-load
// time keep seeing live data. Items pushed in are the same proxies as
// `currentGroup.value.teams[i]` (Vue 3 reactive is idempotent — pushing an
// already-proxied object reuses its proxy), so mutations propagate either
// direction.
const lineups = reactive<Lineup[]>([])

// Seed every workspace so 自由 and 庫存 each start with ≥1 team. The
// watcher below also re-seeds the active group if the user deletes the last
// team; this loop covers the inactive workspace which that watcher never
// sees until a mode switch.
forEachGroup((g) => {
  if (g.teams.length === 0) g.teams.push(makeTeam(0))
})

// Self-bootstrapping: also seeds the active group with one default team if
// it's empty (cold start, or user removed the last team). Folding the seed
// in here removes the seed-then-watch ordering trap an external seed block
// would create. flush:'sync' so a 自由↔庫存 switch reseeds/mirrors before
// currentTeamName reads `.name` (default 'pre' is too late once ElMessage
// or the render effect runs in the same click).
const syncLineupsFromGroup = () => {
  const ws = normalizeWorkspace(catalogMode.value)
  const g = ws.groups[ws.currentGroupIndex]
  if (g.teams.length === 0) g.teams.push(makeTeam(0))
  lineups.splice(0, lineups.length, ...g.teams)
  if (currentTeamIndex.value < 0 || currentTeamIndex.value >= lineups.length) {
    currentTeamIndex.value = Math.max(0, lineups.length - 1)
  }
}

// Watch the computed group reference (not just the index) so wholesale
// replacements via useGroups().replaceGroups() — which the v3 share restore
// uses — also resync the mirror, even if currentGroupIndex stays at 0.
// catalogMode is a second source: undefined→undefined currentGroup would
// otherwise skip the callback on a mode switch.
watch(
  [currentGroup, catalogMode],
  syncLineupsFromGroup,
  { immediate: true, flush: 'sync' },
)

// addTeam / ensureTeamCount mutate the source (currentGroup.teams) AND
// manually mirror the new entries into `lineups`. The watcher does NOT fire
// on in-place pushes — it only fires when `currentGroup`'s identity changes
// (group switch or replaceGroups). Without the manual mirror these helpers
// would silently grow the source while leaving `lineups` short, until the
// next group-identity change resynced it.
const addTeam = (): boolean => {
  const g = currentGroup.value
  if (g.teams.length >= MAX_TEAMS_PER_GROUP) return false
  g.teams.push(makeTeam(g.teams.length))
  // Pull the just-pushed item back from the source array so the value
  // mirrored into `lineups` is the same proxy as currentGroup.teams[i].
  const last = g.teams[g.teams.length - 1]
  lineups.push(last)
  currentTeamIndex.value = lineups.length - 1
  return true
}

// Grow the active group up to `target` slots so a share blob with N teams can
// restore fully. Caller is responsible for not exceeding MAX_TEAMS_PER_GROUP.
const ensureTeamCount = (target: number) => {
  const g = currentGroup.value
  while (g.teams.length < target && g.teams.length < MAX_TEAMS_PER_GROUP) {
    g.teams.push(makeTeam(g.teams.length))
    const last = g.teams[g.teams.length - 1]
    lineups.push(last)
  }
}

// Append a pre-built Lineup (e.g. from a proposal import) and switch to it.
// Caller must pass a fully-formed deep clone — the snapshot becomes part of
// the active group's reactive state.
const addTeamFromSnapshot = (team: Lineup): boolean => {
  const g = currentGroup.value
  if (g.teams.length >= MAX_TEAMS_PER_GROUP) return false
  g.teams.push(team)
  const last = g.teams[g.teams.length - 1]
  lineups.push(last)
  currentTeamIndex.value = lineups.length - 1
  return true
}

// Remove a team from the current group by index, then keep the mirror and
// currentTeamIndex in sync. Auto-seeds an empty team via ensureTeamCount if
// the removal would leave the group with zero teams (Group invariant: >= 1).
// Returns true on success, false if idx is out of range.
const removeTeamFromCurrent = (idx: number): boolean => {
  if (idx < 0 || idx >= lineups.length) return false
  currentGroup.value.teams.splice(idx, 1)
  lineups.splice(idx, 1)
  if (lineups.length === 0) {
    // ensureTeamCount(1) seeds a fresh empty team into both the source and
    // the mirror via its existing push helper.
    ensureTeamCount(1)
    currentTeamIndex.value = 0
  } else if (currentTeamIndex.value >= lineups.length) {
    currentTeamIndex.value = lineups.length - 1
  } else if (currentTeamIndex.value > idx) {
    // The currently-selected team shifted left by one.
    currentTeamIndex.value -= 1
  }
  return true
}

// Read-only placeholder so `.name` / troop-level computeds stay total if
// the mirror is empty mid-switch. Mutations here are discarded on the next
// sync; the flush:'sync' watcher is what actually repairs the mirror.
const fallbackLineup = makeTeam(0)

const currentLineup = computed((): Lineup => {
  const n = lineups.length
  if (n === 0) return fallbackLineup
  const i = currentTeamIndex.value
  if (i >= 0 && i < n) return lineups[i]
  return lineups[n - 1]
})

const currentTeamName = computed({
  get: () => currentLineup.value?.name ?? '',
  set: (val) => {
    const t = currentLineup.value
    if (t) t.name = val
  },
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

export const computeTeamCost = (team: Lineup | null | undefined): number =>
  (team?.main.hero?.cost ?? 0)
  + (team?.vice1.hero?.cost ?? 0)
  + (team?.vice2.hero?.cost ?? 0)

const totalCost = computed(() => computeTeamCost(currentLineup.value))

// Actions
const swapRoles = (roleA: 'main' | 'vice1' | 'vice2', roleB: 'main' | 'vice1' | 'vice2') => {
  if (roleA === roleB) return
  const l = currentLineup.value
  if (!l) return
  const clone = (r: RoleData): RoleData => ({
    ...r,
    stats: { ...r.stats },
    bingxue: { ...r.bingxue, minors: r.bingxue.minors.map(m => ({ ...m })) },
  })
  const temp = clone(l[roleA])
  l[roleA] = clone(l[roleB])
  l[roleB] = temp
}

// 'team'  = clear the 3 roles of the currently-displayed team
// 'group' = clear roles across every team in the current group's lineups
// (No 'all' here — wiping ALL groups lives in useGroups.resetAllWorkspaces since
//  it requires recreating the groups[] array, which useLineups doesn't own.)
const clearLineup = (type: 'team' | 'group') => {
  if (type === 'team') {
    const t = currentLineup.value
    if (!t) return
    t.main = emptyRole()
    t.vice1 = emptyRole()
    t.vice2 = emptyRole()
  }
  if (type === 'group') {
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
    clearLineup,
    swapRoles,
    addTeam,
    addTeamFromSnapshot,
    removeTeamFromCurrent,
    ensureTeamCount,
  }
}
