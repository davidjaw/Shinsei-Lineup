import { reactive, computed, watch, type ComputedRef } from 'vue'
import type { Group, Team } from '../types/group'
import { MAX_TEAMS_PER_GROUP } from '../types/group'
import { CATALOG_MODES, type CatalogMode } from '../constants/gameData'
import { useInventory } from './useInventory'

// Two catalog modes share inventory but keep independent 編組 graphs.
// `groups` / `currentGroup` always point at the active mode's workspace;
// switching 自由↔庫存 swaps identity (no JSON clone — slot v-models stay
// bound to the live team objects of whichever workspace is current).

export interface WorkspaceState {
  groups: Group[]
  currentGroupIndex: number
  currentTeamIndex: number
}

export interface IncomingGroup {
  id?: string
  name: string
  teams: Team[]
}

export interface WorkspaceIncoming {
  groups: IncomingGroup[]
  currentGroupIndex?: number
  currentTeamIndex?: number
}

const workspacePrefix = (mode: CatalogMode): 'f_' | 'i_' =>
  mode === 'free' ? 'f_' : 'i_'

// Cloud rows have no workspace column. `f_` → 自由; everything else
// (legacy unprefixed v4 ids, plus `i_`) → 庫存.
export const workspaceOfClientId = (id: string): CatalogMode =>
  id.startsWith('f_') ? 'free' : 'inventory'

export const makeGroupId = (mode: CatalogMode): string =>
  `${workspacePrefix(mode)}g_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`

const makeDefaultGroup = (mode: CatalogMode): Group => ({
  id: makeGroupId(mode),
  name: '預設',
  teams: [],
})

const workspaces = reactive<Record<CatalogMode, WorkspaceState>>({
  free: {
    groups: [makeDefaultGroup('free')],
    currentGroupIndex: 0,
    currentTeamIndex: 0,
  },
  inventory: {
    groups: [makeDefaultGroup('inventory')],
    currentGroupIndex: 0,
    currentTeamIndex: 0,
  },
})

const activeMode = (): CatalogMode => useInventory().catalogMode.value

const activeWorkspace = (): WorkspaceState => workspaces[activeMode()]

const clampIndex = (idx: number, len: number): number => {
  if (len <= 0) return 0
  if (idx < 0) return 0
  if (idx >= len) return len - 1
  return idx
}

// ≥1 group, indices in range of the lists they index. Team seed (makeTeam)
// lives in useLineups so this file doesn't import it at module-init time.
const normalizeWorkspace = (mode: CatalogMode): WorkspaceState => {
  const ws = workspaces[mode]
  if (ws.groups.length === 0) {
    ws.groups.push(makeDefaultGroup(mode))
    ws.currentGroupIndex = 0
    ws.currentTeamIndex = 0
    return ws
  }
  const gi = clampIndex(ws.currentGroupIndex, ws.groups.length)
  if (gi !== ws.currentGroupIndex) ws.currentGroupIndex = gi
  const teamCount = ws.groups[gi].teams.length
  const ti = clampIndex(ws.currentTeamIndex, teamCount)
  if (ti !== ws.currentTeamIndex) ws.currentTeamIndex = ti
  return ws
}

for (const mode of CATALOG_MODES) normalizeWorkspace(mode)

// Mode switch updates currentTeamIndex immediately (it's derived from
// catalogMode). Run normalize in the same assignment so AppLayout's
// currentTeamName getter never sees an OOB group index.
watch(
  () => useInventory().catalogMode.value,
  (mode) => { normalizeWorkspace(mode) },
  { flush: 'sync' },
)

const groups: ComputedRef<Group[]> = computed(() => activeWorkspace().groups)

const currentGroupIndex = computed({
  get: () => activeWorkspace().currentGroupIndex,
  set: (v) => {
    const ws = activeWorkspace()
    ws.currentGroupIndex = clampIndex(v, ws.groups.length)
  },
})

const currentTeamIndex = computed({
  get: () => activeWorkspace().currentTeamIndex,
  set: (v) => {
    const ws = activeWorkspace()
    const g = ws.groups[ws.currentGroupIndex]
    ws.currentTeamIndex = clampIndex(v, g?.teams.length ?? 0)
  },
})

const currentGroup = computed((): Group => {
  const ws = activeWorkspace()
  return ws.groups[clampIndex(ws.currentGroupIndex, ws.groups.length)]
})

const addGroup = (name = '新編組'): number => {
  const ws = activeWorkspace()
  ws.groups.push({ id: makeGroupId(activeMode()), name, teams: [] })
  return ws.groups.length - 1
}

const removeGroup = (idx: number): boolean => {
  const ws = activeWorkspace()
  if (ws.groups.length <= 1) return false
  if (idx < 0 || idx >= ws.groups.length) return false
  ws.groups.splice(idx, 1)
  normalizeWorkspace(activeMode())
  return true
}

const renameGroup = (idx: number, name: string) => {
  const g = activeWorkspace().groups[idx]
  if (g) g.name = name
}

const setCurrentGroup = (idx: number) => {
  const ws = activeWorkspace()
  if (idx < 0 || idx >= ws.groups.length) return
  ws.currentGroupIndex = idx
  ws.currentTeamIndex = clampIndex(ws.currentTeamIndex, ws.groups[idx].teams.length)
}

const toLiveGroups = (incoming: IncomingGroup[], mode: CatalogMode): Group[] => {
  const source = incoming.length > 0 ? incoming : [{ name: '預設', teams: [] as Team[] }]
  return source.map((g) => ({
    id: g.id ?? makeGroupId(mode),
    name: g.name,
    teams: g.teams,
  }))
}

const replaceWorkspace = (mode: CatalogMode, incoming: WorkspaceIncoming): void => {
  const ws = workspaces[mode]
  const next = toLiveGroups(incoming.groups, mode)
  ws.groups.splice(0, ws.groups.length, ...next)
  ws.currentGroupIndex = incoming.currentGroupIndex ?? 0
  ws.currentTeamIndex = incoming.currentTeamIndex ?? 0
  normalizeWorkspace(mode)
}

// Wholesale replacement of the *active* workspace. Used by share-link
// restore, dialog 整組匯入, and any user action that should not touch
// the other mode. Element identities are new so watchers on `currentGroup`
// fire and useLineups resyncs its mirror.
const replaceGroups = (incoming: IncomingGroup[]) => {
  if (incoming.length === 0) return
  replaceWorkspace(activeMode(), { groups: incoming, currentGroupIndex: 0, currentTeamIndex: 0 })
}

const replaceAllWorkspaces = (incoming: Record<CatalogMode, WorkspaceIncoming>): void => {
  for (const mode of CATALOG_MODES) {
    replaceWorkspace(mode, incoming[mode] ?? { groups: [] })
  }
}

const regenerateCurrentGroupId = (): void => {
  const ws = activeWorkspace()
  const g = ws.groups[ws.currentGroupIndex]
  if (g) g.id = makeGroupId(activeMode())
}

const appendTeamToGroup = (groupIdx: number, team: Team): boolean => {
  const ws = activeWorkspace()
  if (groupIdx < 0 || groupIdx >= ws.groups.length) return false
  const g = ws.groups[groupIdx]
  if (g.teams.length >= MAX_TEAMS_PER_GROUP) return false
  g.teams.push(team)
  return true
}

const resetAllWorkspaces = (): void => {
  for (const mode of CATALOG_MODES) {
    replaceWorkspace(mode, { groups: [], currentGroupIndex: 0, currentTeamIndex: 0 })
  }
}

const findGroupById = (id: string): Group | undefined => {
  for (const mode of CATALOG_MODES) {
    const g = workspaces[mode].groups.find((x) => x.id === id)
    if (g) return g
  }
  return undefined
}

const forEachGroup = (fn: (g: Group, mode: CatalogMode) => void): void => {
  for (const mode of CATALOG_MODES) {
    for (const g of workspaces[mode].groups) fn(g, mode)
  }
}

// A workspace is "pristine" when it still has the post-bootstrap shape:
// one group, zero or one empty team. Used so a share import into 庫存
// can replace that mode's placeholder without touching 自由.
const isPristineWorkspace = (mode?: CatalogMode): boolean => {
  const ws = workspaces[mode ?? activeMode()]
  if (ws.groups.length !== 1) return false
  const g = ws.groups[0]
  if (g.teams.length > 1) return false
  if (g.teams.length === 1) {
    const t = g.teams[0]
    if (t.main?.hero || t.vice1?.hero || t.vice2?.hero) return false
  }
  return true
}

export function useGroups() {
  return {
    workspaces,
    groups,
    currentGroupIndex,
    currentTeamIndex,
    currentGroup,
    addGroup,
    removeGroup,
    renameGroup,
    setCurrentGroup,
    replaceGroups,
    replaceWorkspace,
    replaceAllWorkspaces,
    regenerateCurrentGroupId,
    resetAllWorkspaces,
    appendTeamToGroup,
    findGroupById,
    forEachGroup,
    isPristineWorkspace,
    normalizeWorkspace,
  }
}
