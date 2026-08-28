// Pure serialize + restore helpers shared by:
//   - share-link export / import (LineupBuilder.vue)
//   - localStorage autosave (useGroupPersistence.ts)
//   - 5-min OAuth recovery snapshot (LineupBuilder.vue snapshotForRecovery)
//
// Lives outside any composable so the same code path serializes/restores
// regardless of caller, and so the healing-pass behaviour (soft-null on
// unresolved JP keys) is enforced everywhere — not just in one codepath.

import type { Hero, Skill } from '../composables/useData'
import {
  emptyRole,
  makeTeam,
  type Lineup,
  type RoleData,
  type BingxueActive,
} from '../composables/useLineups'
import { MAX_TEAMS_PER_GROUP } from '../types/group'
import type { IncomingGroup, WorkspaceIncoming } from '../composables/useGroups'
import {
  CATALOG_MODES,
  type CatalogMode,
  type ShareableBingxue,
  type ShareableData,
  type ShareableGroup,
  type ShareableLineup,
  type ShareableWorkspace,
} from '../constants/gameData'

export interface SerializeDeps {
  heroes: Hero[]
  skills: Skill[]
}

// "Empty" in serialized form mirrors useLineups.isEmptyTeam: a team is
// empty when none of the three roles has a hero key set. Skills / stats /
// breakthrough / bingxue without a hero have no game meaning and are
// effectively dead weight in merge/preview displays.
export const isEmptyShareableLineup = (l: ShareableLineup): boolean =>
  !l.m && !l.v1 && !l.v2

const serializeBx = (bx: BingxueActive): ShareableBingxue => ({
  d: bx.direction,
  m: bx.major,
  n: bx.minors.map((mi) => ({ n: mi.name, l: mi.level })),
})

// Factory: returns serializers bound to a heroes/skills lookup. Caller passes
// the current data refs (e.g. from useData) — the maps are built once and
// reused across all roles in a save round.
export function makeSerializer(deps: SerializeDeps) {
  const heroChtToJp = new Map(deps.heroes.map((h) => [h.name, h.name_jp]))
  const skillChtToJp = new Map(deps.skills.map((s) => [s.name, s.name_jp]))

  const toJpHero = (cht?: string): string | undefined =>
    cht ? heroChtToJp.get(cht) ?? cht : undefined
  const toJpSkill = (cht?: string): string | undefined =>
    cht ? skillChtToJp.get(cht) ?? cht : undefined

  const serializeRole = (
    r: RoleData,
    prefix: 'm' | 'v1' | 'v2',
  ): Partial<ShareableLineup> =>
    ({
      [prefix]: toJpHero(r.hero?.name),
      [`${prefix}_s1`]: toJpSkill(r.skill1?.name),
      [`${prefix}_s2`]: toJpSkill(r.skill2?.name),
      [`${prefix}_st`]: r.stats,
      [`${prefix}_bt`]: r.breakthrough,
      [`${prefix}_bx`]: serializeBx(r.bingxue),
    }) as Partial<ShareableLineup>

  const serializeLineup = (l: Lineup): ShareableLineup => ({
    name: l.name,
    ...serializeRole(l.main, 'm'),
    ...serializeRole(l.vice1, 'v1'),
    ...serializeRole(l.vice2, 'v2'),
  })

  return { toJpHero, toJpSkill, serializeLineup }
}

// Tracks JP keys that failed to resolve during a restore. Aggregated so the
// caller can surface a single "N entries cleared" toast instead of per-slot
// spam. We don't carry the kind (hero/skill) — the user-facing message is
// the same either way and the field name (e.g. `hero:某太郎`) survives the
// dedupe via the prefix.
export interface RestoreReport {
  /** Prefixed JP keys, e.g. `hero:山縣昌景` or `skill:武田之赤備` */
  healed: string[]
  /** The active group index found in the blob, if any. Caller decides
   *  whether/when to apply it (after replaceGroups has run). */
  activeIndex: number | null
}

const mintWorkspaceGroupId = (mode: CatalogMode): string =>
  `${mode === 'free' ? 'f_' : 'i_'}g_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`

export const blobHasTeams = (data: ShareableData): boolean => {
  if (data.workspaces) {
    return CATALOG_MODES.some((m) => (data.workspaces?.[m]?.groups?.length ?? 0) > 0)
  }
  return !!(data.groups && data.groups.length > 0) || !!(data.lineups && data.lineups.length > 0)
}

export const blobHasInventory = (data: ShareableData): boolean =>
  !!(data.inv_h && data.inv_h.length > 0)
  || !!(data.inv_s && data.inv_s.length > 0)
  || !!(data.inventory && data.inventory.length > 0)

// Flatten v5 workspaces (or legacy top-level groups) into one list. Used by
// cloud push, merge-dialog previews, and any caller that wants "all groups
// in this blob" without caring which mode they belong to.
export const shareableGroupsInBlob = (data: ShareableData): ShareableGroup[] => {
  if (data.workspaces) {
    return CATALOG_MODES.flatMap((m) => data.workspaces?.[m]?.groups ?? [])
  }
  return data.groups ?? []
}

// Groups a user-facing import should apply to the *current* mode. Prefers
// the matching v5 workspace, then legacy `groups` / `lineups`. Never falls
// back to the other workspace — empty current mode stays empty.
export const shareableGroupsForMode = (
  data: ShareableData,
  mode: CatalogMode,
): ShareableGroup[] => {
  const own = data.workspaces?.[mode]?.groups
  if (own && own.length > 0) return own
  if (data.groups && data.groups.length > 0) return data.groups
  if (data.lineups && data.lineups.length > 0) {
    return [{ name: '匯入的編組', teams: data.lineups }]
  }
  return []
}

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

const findHeroByKey = (heroes: Hero[], key: string): Hero | undefined =>
  getHeroLookup(heroes).get(key)

const findSkillByKey = (skills: Skill[], key: string): Skill | undefined =>
  getSkillLookup(skills).get(key)

// Per-role hydrate with healing. Mutates `role` in place.
//
// Behaviour:
//   - hero JP key fails to resolve → reset entire role to emptyRole(), skip
//     remaining fields. Prevents the legacy bug where a null hero kept the
//     previous occupant's skills/stats/breakthrough/bingxue, which then
//     surfaced as "ghost data" in the UI.
//   - skill JP key fails → null that skill slot only, record the JP key.
//   - stats is shallow-copied so dual hydrate never shares the same object.
//   - breakthrough / bingxue are copied as-is when present.
const restoreRoleInto = (
  prefix: string,
  role: RoleData,
  l: ShareableLineup,
  deps: SerializeDeps,
  report: string[],
): void => {
  const safeL = l as unknown as Record<string, unknown>

  const hName = safeL[prefix] as string | undefined
  if (hName) {
    const h = findHeroByKey(deps.heroes, hName)
    if (h) {
      role.hero = h
    } else {
      report.push(`hero:${hName}`)
      // Reset the whole role — see comment above.
      Object.assign(role, emptyRole())
      return
    }
  }

  const s1Name = safeL[`${prefix}_s1`] as string | undefined
  if (s1Name) {
    const s = findSkillByKey(deps.skills, s1Name)
    if (s) role.skill1 = s
    else {
      report.push(`skill:${s1Name}`)
      role.skill1 = null
    }
  }

  const s2Name = safeL[`${prefix}_s2`] as string | undefined
  if (s2Name) {
    const s = findSkillByKey(deps.skills, s2Name)
    if (s) role.skill2 = s
    else {
      report.push(`skill:${s2Name}`)
      role.skill2 = null
    }
  }

  const st = safeL[`${prefix}_st`]
  if (st) role.stats = { ...(st as RoleData['stats']) }

  const bt = safeL[`${prefix}_bt`]
  if (typeof bt === 'number') role.breakthrough = Math.max(0, Math.min(5, bt))

  const bx = safeL[`${prefix}_bx`] as
    | { d?: string; m?: string; n?: { n: string; l: number }[] }
    | undefined
  if (bx?.d) {
    role.bingxue = {
      direction: bx.d as BingxueActive['direction'],
      major: bx.m ?? null,
      minors: Array.isArray(bx.n)
        ? bx.n.map((mi) => ({ name: mi.n, level: mi.l as 1 | 2 }))
        : [],
    }
  }
}

// Build a fresh Lineup from a ShareableLineup. Used by the v3/v4 groups
// envelope path which wipes-and-replaces the active group via replaceGroups.
const buildTeamFromShareable = (
  l: ShareableLineup,
  idx: number,
  deps: SerializeDeps,
  report: string[],
): Lineup => {
  const team = makeTeam(idx)
  if (l.name) team.name = l.name
  restoreRoleInto('m', team.main, l, deps, report)
  restoreRoleInto('v1', team.vice1, l, deps, report)
  restoreRoleInto('v2', team.vice2, l, deps, report)
  return team
}

// Public wrapper for the import flows (share-link, cross-group). Returns
// the rebuilt Lineup alongside the deduped healing report so callers can
// surface a "N entries auto-cleared" toast without having to manage the
// report array themselves. The full applyBlobToState path is too broad
// for these flows — it wipes the active group via replaceGroups, whereas
// importers want to append a single team or build a list of teams to
// stitch into the existing groups[].
export const hydrateShareableTeam = (
  l: ShareableLineup,
  idx: number,
  deps: SerializeDeps,
): { team: Lineup; healed: string[] } => {
  const report: string[] = []
  const team = buildTeamFromShareable(l, idx, deps, report)
  return { team, healed: Array.from(new Set(report)) }
}

// In-place hydrate of an existing Lineup (used by the v2 legacy path which
// mutates the active group's teams[] rather than wholesale-replacing).
const hydrateTeamInPlace = (
  target: Lineup,
  l: ShareableLineup,
  deps: SerializeDeps,
  report: string[],
): void => {
  if (l.name) target.name = l.name
  restoreRoleInto('m', target.main, l, deps, report)
  restoreRoleInto('v1', target.vice1, l, deps, report)
  restoreRoleInto('v2', target.vice2, l, deps, report)
}

// Inventory restore — converts JP keys back to CHT names. Drops keys that
// fail to resolve entirely (legacy null/empty entries from old Supabase
// rows). Returned strings are CHT names suitable for direct assignment to
// ownedHeroes/ownedSkills.
const toChtArray = <T extends { name: string }>(
  arr: string[],
  finder: (k: string) => T | undefined,
): string[] => arr.map((k) => finder(k)?.name ?? k).filter(Boolean)

export const hydrateShareableGroups = (
  groups: ShareableGroup[],
  deps: SerializeDeps,
  report: string[],
): IncomingGroup[] =>
  groups.map((g) => {
    const teams = (g.teams || [])
      .slice(0, MAX_TEAMS_PER_GROUP)
      .map((l, i) => buildTeamFromShareable(l, i, deps, report))
    if (teams.length === 0) teams.push(makeTeam(0))
    return { id: g.id, name: g.name || '預設', teams }
  })

// v4→v5: copy the single group list into BOTH workspaces. Inventory keeps
// the original ids so existing cloud (user_id, client_id) rows keep
// PATCHing; free gets freshly minted `f_` ids so the unique index does
// not collide. Users currently see the same board in both filters —
// copy-then-diverge is less surprising than emptying one side.
export const wrapV4AsV5 = (data: ShareableData): ShareableData => {
  if (data.workspaces) return { ...data, v: 5 }
  const groups = data.groups ?? []
  const idx = typeof data.active_group_index === 'number' ? data.active_group_index : 0
  const cloneGroup = (g: ShareableGroup, mintFreeId: boolean): ShareableGroup => {
    const cloned = structuredClone(g)
    cloned.id = mintFreeId ? mintWorkspaceGroupId('free') : g.id
    cloned.teams = cloned.teams ?? []
    return cloned
  }
  const workspaces: Record<CatalogMode, ShareableWorkspace> = {
    inventory: {
      active_group_index: idx,
      groups: groups.map((g) => cloneGroup(g, false)),
    },
    free: {
      active_group_index: idx,
      groups: groups.map((g) => cloneGroup(g, true)),
    },
  }
  return { ...data, v: 5, workspaces }
}

// State refs that applyBlobToState mutates. Passing them as deps keeps this
// module pure — no module-level singletons, no useX() calls inside.
export interface ApplyBlobDeps extends SerializeDeps {
  ownedHeroes: { value: string[] }
  ownedSkills: { value: string[] }
  lineups: Lineup[]
  ensureTeamCount: (target: number) => void
  replaceGroups: (groups: IncomingGroup[]) => void
  replaceAllWorkspaces?: (incoming: Record<CatalogMode, WorkspaceIncoming>) => void
  activeMode?: CatalogMode
}

export type ApplyBlobScope = 'active' | 'all'

const applyInventory = (data: ShareableData, deps: ApplyBlobDeps): void => {
  if (data.inventory) {
    deps.ownedHeroes.value = toChtArray(data.inventory, (k) =>
      findHeroByKey(deps.heroes, k),
    )
  }
  if (data.inv_h) {
    deps.ownedHeroes.value = toChtArray(data.inv_h, (k) =>
      findHeroByKey(deps.heroes, k),
    )
  }
  if (data.inv_s) {
    deps.ownedSkills.value = toChtArray(data.inv_s, (k) =>
      findSkillByKey(deps.skills, k),
    )
  }
}

const applyGroupsToActive = (
  groups: ShareableGroup[],
  deps: ApplyBlobDeps,
  report: string[],
): void => {
  const incoming = hydrateShareableGroups(groups, deps, report)
  if (incoming.length === 0) return
  deps.replaceGroups(incoming)
}

// Top-level restore. `scope: 'all'` (autosave / cloud / OAuth) writes both
// workspaces; `scope: 'active'` (share-link / dialog import) writes only
// the currently selected mode and never wipes the other.
export const applyBlobToState = (
  data: ShareableData,
  deps: ApplyBlobDeps,
  opts?: { scope?: ApplyBlobScope },
): RestoreReport => {
  const report: string[] = []
  const scope: ApplyBlobScope = opts?.scope ?? 'active'

  applyInventory(data, deps)

  if (scope === 'all' && deps.replaceAllWorkspaces && (data.workspaces || (data.groups && data.groups.length > 0))) {
    const v5 = wrapV4AsV5(data)
    const incoming = {} as Record<CatalogMode, WorkspaceIncoming>
    for (const mode of CATALOG_MODES) {
      const ws = v5.workspaces?.[mode]
      incoming[mode] = {
        groups: hydrateShareableGroups(ws?.groups ?? [], deps, report),
        currentGroupIndex: ws?.active_group_index ?? 0,
        currentTeamIndex: ws?.active_team_index ?? 0,
      }
    }
    deps.replaceAllWorkspaces(incoming)
    return {
      healed: Array.from(new Set(report)),
      activeIndex: incoming[deps.activeMode ?? 'free']?.currentGroupIndex ?? 0,
    }
  }

  const mode = deps.activeMode ?? 'free'
  const groupsForActive = data.workspaces
    ? shareableGroupsForMode(data, mode)
    : (data.groups ?? [])
  if (groupsForActive.length > 0) {
    applyGroupsToActive(groupsForActive, deps, report)
  } else if (!data.workspaces && data.lineups && data.lineups.length > 0) {
    // v1/v2 legacy — in-place mutate the active group's teams.
    deps.ensureTeamCount(data.lineups.length)
    data.lineups.forEach((l, i) => {
      if (i >= deps.lineups.length) return
      hydrateTeamInPlace(deps.lineups[i], l, deps, report)
    })
  }

  return {
    healed: Array.from(new Set(report)),
    activeIndex: data.workspaces
      ? (data.workspaces[mode]?.active_group_index ?? null)
      : (typeof data.active_group_index === 'number' ? data.active_group_index : null),
  }
}
