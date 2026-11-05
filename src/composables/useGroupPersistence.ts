// Phase A + C — localStorage autosave AND opt-in cloud sync for 編組.
//
// Two channels, one source of truth:
//   - localStorage (Phase A): ~800ms debounce, every reactive edit. Works
//     for anon + signed-in users. The session-level source of truth.
//   - Supabase lineup_groups (Phase C): ~1800ms debounce, only when signed
//     in and cloudSyncEnabled. Cross-device mirror of the local state.
//
// Why a separate composable (not folded into useGroups):
//   - useLineups owns a watch(currentGroup, syncLineupsFromGroup) that fires
//     on every group identity change. Adding a save-on-change watch inside
//     useGroups risks circular reactivity. Persistence sits as a separate
//     orchestrator that reads the live state and writes to storage / cloud.
//   - LineupBuilder.vue already owns the share-link / OAuth-recovery
//     restore flow; this composable adds the autosave channel without
//     touching that ordering.
//
// Cross-tab strategy (risk #2 from the backend review):
//   BroadcastChannel + monotonic `gen` counter inside the blob. Each tab
//   increments its gen on save; on receiving a saved message from another
//   tab whose gen is higher than ours, we re-read localStorage and
//   reconcile. Last-writer-wins per debounce window, with a short
//   `suppressWritesUntil` time window that drops reactive echoes when
//   applying an incoming message. We deliberately do NOT listen to `storage`:
//   `storage` doesn't fire on the writing tab, which would require a second
//   "I just saved" channel for status UI later; BroadcastChannel covers both.
//
// active_group_index (risk #5):
//   Stored per workspace inside the v5 blob and applied inside
//   replaceWorkspace during restoreFromLocalStorage().
//
// Healing (risk #4):
//   applyBlobToState returns a `healed` array of JP keys that failed to
//   resolve. The host view watches `healingReport` and toasts an aggregate
//   count.
//
// Cloud conflict (risk #3):
//   Per-row optimistic lock via &updated_at=eq.<iso>. A 0-row PATCH
//   response → conflict; we surface the 'cloud-conflict' dialog with the
//   server row vs the local group, and the user picks: use cloud / overwrite
//   cloud / defer (turn sync off for this session).
//
// Anon → signed-in handoff (risk #1):
//   2x2 table inside tryBootstrapCloudSync. Both-non-empty is the only
//   path that prompts; the other three corners apply silently.

import { reactive, ref, watch } from 'vue'
import { useData } from './useData'
import { useGroups } from './useGroups'
import { useLineups, isEmptyTeam, type Lineup } from './useLineups'
import { useInventory } from './useInventory'
import { useAuth } from './useAuth'
import { useDialogs } from './useDialogs'
import {
  applyBlobToState,
  hydrateShareableGroups,
  isEmptyShareableLineup,
  makeSerializer,
  shareableGroupsInBlob,
  wrapV4AsV5,
  type ApplyBlobDeps,
} from '../lib/lineupSerialize'
import {
  bulkCreateLineupGroups,
  createLineupGroup,
  deleteLineupGroup,
  groupContentHash,
  listMyLineupGroups,
  patchLineupGroupForce,
  patchLineupGroupWithLock,
  stableStringify,
  type CloudLineupGroup,
} from '../lib/lineupGroups'
import { createShare } from '../lib/share'
import { onSessionEvent } from '../lib/auth'
import { CATALOG_MODES, type CatalogMode, type ShareableData, type ShareableGroup } from '../constants/gameData'
import { workspaceOfClientId } from './useGroups'

const STORAGE_KEY = 'nobunaga.groups.v5'
const LEGACY_STORAGE_KEY = 'nobunaga.groups.v4'
const DEVICE_ID_KEY = 'nobunaga.device.id'
const CLOUD_SYNC_PREF_KEY = 'nobunaga.cloud_sync_enabled'
// Per-user persisted meta map. Used as the "we've already synced on this
// device for this user" signal so reloads don't re-prompt the merge dialog
// when local + cloud are already in sync. Keyed by user_id so a different
// user signing in on the same device gets a fresh handoff.
const CLOUD_META_KEY_PREFIX = 'nobunaga.cloud_sync_meta.'
const BROADCAST_CHANNEL_NAME = 'nobunaga.groups'
const LOCAL_DEBOUNCE_MS = 800
const CLOUD_DEBOUNCE_MS = 1800

// Module-singleton state — same pattern as useGroups / useLineups so any
// component can pull the composable without re-wiring watchers.
const healingReport = ref<string[]>([])
let localGen = 0
// Time-window suppression for reactive echoes. When we apply an incoming
// blob (cross-tab message, merge dialog choice, conflict resolution), the
// resulting replaceGroups() triggers our deep watcher — but those writes
// would loop the same data back to disk / cloud. A single boolean isn't
// enough because Vue may batch reactive updates across multiple ticks for
// a single replaceGroups call. We instead arm a short time window
// (SUPPRESS_WINDOW_MS) during which a firing write is dropped. The window is
// shorter than the debounce, so most echoes outlive it; those are dropped in
// writeBlobToStorage because their content matches what is already stored.
const SUPPRESS_WINDOW_MS = 50
let suppressWritesUntil = 0
let debounceHandle: number | null = null
let cloudDebounceHandle: number | null = null
let bc: BroadcastChannel | null = null
let autosaveEnabled = false
let cloudBootstrapped = false
let bootstrapInFlight = false
let bootstrapGeneration = 0
let bootstrapFlightGen = 0  // generation that currently owns the mutex
let skipCloudHydrate = false  // session wipe-intent; not persisted

// Cloud-sync reactive surface — components subscribe via useGroupPersistence().
const cloudSyncEnabled = ref<boolean>(loadCloudSyncPref())
const cloudStatus = ref<
  'idle' | 'syncing' | 'conflict' | 'offline' | 'error'
>('idle')

// Set by "稍後再決定" in the merge dialog: the user has not said which side
// wins, so no push may run until they do. Local autosave continues.
const cloudMergeDeferred = ref(false)

// Maps a local ShareableGroup.id (client_id) to its corresponding cloud row
// id + the updated_at observed at the last successful read/write. The
// updated_at is the optimistic-lock precondition for the next PATCH.
// contentHash + sortOrder are what local held at that moment; a PATCH with both
// equal is skipped so an unchanged group does not invalidate other clients'
// locks. A missing hash (meta persisted by an older version) means "assume changed".
// removed: the user removed this group in a tab that held it, so stale-delete
// may delete the row. Nothing else authorizes a delete.
// rowGone: another client deleted the row while local had no edit to upload.
interface CloudGroupMeta {
  cloudId: string
  serverUpdatedAt: string
  contentHash?: string
  sortOrder?: number
  removed?: boolean
  rowGone?: boolean
}

const cloudGroupsByClientId = reactive(new Map<string, CloudGroupMeta>())

// Surfaces the conflict dialog. Populated when a PATCH hits the
// precondition-failed (0-row) response. Cleared by the dialog's resolution
// handlers.
const cloudConflict = ref<{
  localGroupId: string  // ShareableGroup.id of the local group whose push conflicted
  serverRow: CloudLineupGroup
} | null>(null)

// Surfaces the merge-on-sign-in dialog. Populated by tryBootstrapCloudSync
// when both local and cloud are non-empty. Cleared by the dialog's choice
// handlers.
const cloudMerge = ref<{
  localBlob: ShareableData
  cloudRows: CloudLineupGroup[]
} | null>(null)

function loadCloudSyncPref(): boolean {
  try {
    return localStorage.getItem(CLOUD_SYNC_PREF_KEY) !== 'false'
  } catch {
    return true
  }
}

function persistCloudSyncPref(v: boolean): void {
  try {
    localStorage.setItem(CLOUD_SYNC_PREF_KEY, v ? 'true' : 'false')
  } catch {
    /* swallow — quota / private browsing */
  }
}

// Persist the in-memory cloudGroupsByClientId snapshot for the given user.
// Called after every successful sync operation so a reload can skip the
// 2x2 bootstrap (and its merge dialog) when we've already synced.
type PersistedCloudMeta = Record<string, CloudGroupMeta> // keyed by client_id

const cloudMetaKey = (userId: string): string => `${CLOUD_META_KEY_PREFIX}${userId}`

// The stored meta this tab last read or wrote. A different value in storage
// means a sibling tab pushed since.
let lastSeenMetaRaw: string | null = null

const loadPersistedCloudMeta = (userId: string): PersistedCloudMeta | null => {
  try {
    const raw = localStorage.getItem(cloudMetaKey(userId))
    lastSeenMetaRaw = raw
    return raw ? (JSON.parse(raw) as PersistedCloudMeta) : null
  } catch {
    return null
  }
}

const writePersistedCloudMeta = (userId: string): void => {
  try {
    const obj: PersistedCloudMeta = {}
    cloudGroupsByClientId.forEach((v, k) => {
      obj[k] = { ...v }
    })
    const raw = JSON.stringify(obj)
    localStorage.setItem(cloudMetaKey(userId), raw)
    lastSeenMetaRaw = raw
  } catch {
    /* swallow — quota / private browsing */
  }
}

// Convenience — called from every code path that mutates cloudGroupsByClientId
// so persistence stays in lockstep with the in-memory map. No-op when the
// user is anonymous (shouldn't be reached anyway, but defensive).
const syncCloudMetaToStorage = (): void => {
  const { user } = useAuth()
  const userId = user.value?.id
  if (!userId) return
  writePersistedCloudMeta(userId)
}

// Pick up locks a sibling tab stored since we last looked. Without this, this
// tab's next write would conflict with its own sibling. Keeps the in-memory map
// when storage is unchanged, including when storage writes are failing. A tab
// that missed a sibling's save keeps its own locks: its copies of the rows the
// sibling moved are stale, so writing them must raise a conflict, not succeed.
const reloadCloudMetaFromStorage = (): void => {
  const userId = useAuth().user.value?.id
  if (!userId || missedSiblingSave) return
  const raw = localStorage.getItem(cloudMetaKey(userId))
  if (raw === null || raw === lastSeenMetaRaw) return
  const persisted = loadPersistedCloudMeta(userId)
  if (!persisted) return
  cloudGroupsByClientId.clear()
  for (const [clientId, meta] of Object.entries(persisted)) {
    cloudGroupsByClientId.set(clientId, meta)
  }
}

// Authorize stale-delete for these rows, in memory and in storage: the map may be
// empty (sync off) or behind a sibling, and the delete may only run after a reload.
const markRowsRemoved = (clientIds: string[]): void => {
  const userId = useAuth().user.value?.id
  if (!userId) return
  for (const id of clientIds) {
    const meta = cloudGroupsByClientId.get(id)
    if (meta) meta.removed = true
  }
  try {
    const raw = localStorage.getItem(cloudMetaKey(userId))
    if (!raw) return
    const stored = JSON.parse(raw) as PersistedCloudMeta
    for (const id of clientIds) {
      if (stored[id]) stored[id].removed = true
    }
    localStorage.setItem(cloudMetaKey(userId), JSON.stringify(stored))
  } catch {
    /* swallow — quota / private browsing */
  }
}

// Drop ALL persisted cloud meta entries (every user key under the prefix).
// Called on signed-out / expired session events: persisted meta represents
// "this device was in sync with cloud at moment of sync", which becomes
// false the instant the user logs out — they can mutate local arbitrarily
// while signed out, and the next sign-in must re-verify via the 2x2.
// Scanning by prefix (rather than passing a single userId) keeps this safe
// across account switches and works even when the session has already been
// torn down by the time this listener fires.
const clearPersistedCloudMeta = (): void => {
  try {
    const keysToRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(CLOUD_META_KEY_PREFIX)) keysToRemove.push(k)
    }
    for (const k of keysToRemove) localStorage.removeItem(k)
    lastSeenMetaRaw = null
  } catch {
    /* swallow */
  }
}

// Lazy device_id — created on first read, persists across reloads. Used in
// every save to differentiate "I just wrote this" from "another tab wrote it".
const getOrCreateDeviceId = (): string => {
  let id = localStorage.getItem(DEVICE_ID_KEY)
  if (!id) {
    // crypto.randomUUID is available in all evergreen browsers we target.
    id = `dev_${crypto.randomUUID()}`
    localStorage.setItem(DEVICE_ID_KEY, id)
  }
  return id
}

// Seed localGen from the existing blob at module load so a reload doesn't
// reset to 0 and confuse cross-tab race detection (other tabs would all
// look "newer" by gen and trigger needless reconciliations).
const readStoredRaw = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY)
  } catch {
    return null
  }
}

const seedLocalGen = (): void => {
  try {
    const raw = readStoredRaw()
    if (!raw) return
    const blob = JSON.parse(raw) as ShareableData
    localGen = typeof blob.gen === 'number' ? blob.gen : 0
  } catch {
    localGen = 0
  }
}
seedLocalGen()

// Helpers ----------------------------------------------------------------

// "Empty" for the merge decision — zero groups, OR all groups contain only
// empty teams. A fresh seeded group (one empty team) counts as empty.
const isEmptyGroupSet = (groups: { teams: Lineup[] }[]): boolean => {
  for (const g of groups) {
    for (const t of g.teams) {
      if (!isEmptyTeam(t)) return false
    }
  }
  return true
}

const firstNonEmptyShareableIndex = (
  groups: { teams: CloudLineupGroup['teams'] }[],
): number => {
  const idx = groups.findIndex((g) => g.teams.some((t) => !isEmptyShareableLineup(t)))
  return idx === -1 ? 0 : idx
}

// Build the v5 ShareableData blob from the current live state. Pure with
// respect to the state refs it reads.
//
// `bumpGen` controls whether localGen is incremented — set true on the
// write paths (localStorage autosave, cloud upload, post-merge cloud push)
// so cross-tab `gen` comparisons see fresh values; set false for read-only
// snapshots (OAuth recovery, merge dialog context capture) so the counter
// doesn't drift ahead of what was actually persisted.
const buildBlob = (bumpGen = true): ShareableData => {
  const { heroes, skills } = useData()
  const { workspaces } = useGroups()
  const { ownedHeroes, ownedSkills } = useInventory()

  const serializer = makeSerializer({
    heroes: heroes.value,
    skills: skills.value,
  })
  if (bumpGen) localGen += 1

  const now = new Date().toISOString()
  const serializeWs = (mode: CatalogMode) => {
    const ws = workspaces[mode]
    return {
      active_group_index: ws.currentGroupIndex,
      active_team_index: ws.currentTeamIndex,
      groups: ws.groups.map((g) => ({
        id: g.id,
        name: g.name,
        updated_at: now,
        teams: g.teams.map((t) => serializer.serializeLineup(t)),
      })),
    }
  }

  return {
    v: 5,
    device_id: getOrCreateDeviceId(),
    gen: localGen,
    saved_at: now,
    inv_h: ownedHeroes.value.map((n) => serializer.toJpHero(n) ?? n),
    inv_s: ownedSkills.value.map((n) => serializer.toJpSkill(n) ?? n),
    workspaces: {
      free: serializeWs('free'),
      inventory: serializeWs('inventory'),
    },
  }
}

// Centralized deps factory — keeps applyBlobToState's argument list explicit
// and lets restore() / cross-tab reconcile / merge dialog share the same wiring.
const buildApplyDeps = (): ApplyBlobDeps => {
  const { heroes, skills } = useData()
  const { lineups, ensureTeamCount } = useLineups()
  const { replaceGroups, replaceAllWorkspaces } = useGroups()
  const { ownedHeroes, ownedSkills, catalogMode } = useInventory()
  return {
    heroes: heroes.value,
    skills: skills.value,
    ownedHeroes,
    ownedSkills,
    lineups,
    ensureTeamCount,
    replaceGroups,
    replaceAllWorkspaces,
    activeMode: catalogMode.value,
  }
}

// Apply an arbitrary ShareableData blob to state. Used by the cross-tab
// reconciler and (indirectly) by the merge dialog's "use cloud" path.
const applyBlobToLiveState = (blob: ShareableData): void => {
  const deps = buildApplyDeps()
  // Autosave / cross-tab / OAuth / cloud always restore BOTH workspaces.
  const { healed } = applyBlobToState(blob, deps, { scope: 'all' })
  if (healed.length > 0) healingReport.value = healed
}

// OAuth-recovery snapshot ----------------------------------------------
// Captures full live state under a 5-min TTL'd localStorage key, so the
// post-redirect mount can restore everything the user had in flight.
// Triggered by any view that initiates `signIn` (LineupBuilder /
// AppLayout's UserControls). The restore side (consumeRecovery) is only
// useful from LineupBuilder because applyBlobToLiveState writes back into
// the lineup builder state graph.
const RECOVERY_KEY = 'nobunaga.auth.recovery'
const RECOVERY_TTL_MS = 5 * 60 * 1000

const snapshotForRecovery = (): void => {
  try {
    localStorage.setItem(
      RECOVERY_KEY,
      JSON.stringify({ blob: buildBlob(false), ts: Date.now() }),
    )
  } catch {
    // localStorage full / disabled — silent drop is fine, the user just
    // loses their in-progress lineup if they actually complete OAuth.
  }
}

const consumeRecovery = (): boolean => {
  const raw = localStorage.getItem(RECOVERY_KEY)
  if (!raw) return false
  localStorage.removeItem(RECOVERY_KEY)
  try {
    const { blob, ts } = JSON.parse(raw) as { blob: ShareableData; ts: number }
    if (Date.now() - ts > RECOVERY_TTL_MS) return false
    applyBlobToLiveState(blob)
    return true
  } catch {
    return false
  }
}

const rowToShareableGroup = (r: CloudLineupGroup): ShareableGroup => ({
  id: r.client_id ?? r.id, // fall back to db id when client_id was never set (cloud-first row)
  name: r.name,
  updated_at: r.updated_at,
  teams: r.teams,
})

const splitCloudRowsByWorkspace = (
  rows: CloudLineupGroup[],
): Record<CatalogMode, ShareableGroup[]> => {
  const out: Record<CatalogMode, ShareableGroup[]> = { free: [], inventory: [] }
  for (const r of rows) {
    const id = r.client_id ?? r.id
    out[workspaceOfClientId(id)].push(rowToShareableGroup(r))
  }
  return out
}

// Build a ShareableData blob from a list of cloud rows. Mirror of the v5
// shape produced by buildBlob, with values pulled from the cloud rather
// than from local state. Unprefixed (v4) rows all land in 庫存; if the
// cloud has no `f_` rows at all we treat it as a pre-split snapshot and
// copy into both workspaces (same v4→v5 local migration).
const cloudRowsToBlob = (rows: CloudLineupGroup[]): ShareableData => {
  const hasFreePrefix = rows.some((r) => (r.client_id ?? r.id).startsWith('f_'))
  if (!hasFreePrefix && rows.length > 0) {
    return wrapV4AsV5({
      v: 4,
      groups: rows.map(rowToShareableGroup),
    })
  }
  const split = splitCloudRowsByWorkspace(rows)
  return {
    v: 5,
    workspaces: {
      free: {
        active_group_index: firstNonEmptyShareableIndex(split.free),
        groups: split.free,
      },
      inventory: {
        active_group_index: firstNonEmptyShareableIndex(split.inventory),
        groups: split.inventory,
      },
    },
  }
}

// Tab-local knowledge of the saved state ----------------------------------

// Ids this tab has held as live local groups. Only a group that leaves this set
// through a local edit counts as removed by the user. Groups replaced by a
// sibling's blob or a cloud pull do not: that tab's copy may simply be older.
let heldGroupIds: ReadonlySet<string> | null = null

const liveGroupIds = (): Set<string> => {
  const { workspaces } = useGroups()
  return new Set(
    CATALOG_MODES.flatMap((m) => workspaces[m].groups.map((g) => g.id).filter(Boolean)),
  )
}

// Once, before the user can act: a later seed would miss a removal made before it.
const seedHeldGroups = (): void => {
  if (!heldGroupIds) heldGroupIds = liveGroupIds()
}

const noteRemovedGroups = (): void => {
  const live = liveGroupIds()
  const removed = [...(heldGroupIds ?? [])].filter((id) => !live.has(id))
  heldGroupIds = live
  if (removed.length > 0) markRowsRemoved(removed)
}

// The stored blob this tab last wrote or applied. A different value in storage
// is a sibling's save this tab did not apply (a dialog was open, or the two
// saves had the same gen).
let lastSeenBlobRaw: string | null = null
let missedSiblingSave = false

const storedBlobIsUnseen = (): boolean => {
  if (!localRestoreAttempted) return false
  const raw = readStoredRaw()
  return raw !== null && raw !== lastSeenBlobRaw
}

// While these are open the tab must not take in a sibling's blob: their snapshots
// (capacity, hydrated teams, name collisions) would diverge mid-decision.
const siblingUpdatesBlocked = (): boolean => {
  if (cloudMerge.value || cloudConflict.value) return true
  const { active } = useDialogs()
  return active.value === 'import-from-link'
    || active.value === 'import-handbook'
    || active.value === 'export-team-to-group'
}

// Keep groups a sibling saved that this tab never knew, so saving does not erase
// them from the stored blob. Known groups are left alone: one missing from the
// local copy was removed here, and one that differs goes through the row lock.
const adoptUnseenSiblingGroups = (): void => {
  const raw = readStoredRaw()
  if (!raw) return
  const { heroes, skills } = useData()
  const { workspaces } = useGroups()
  const stored = wrapV4AsV5(JSON.parse(raw) as ShareableData)
  const known = new Set([...(heldGroupIds ?? []), ...liveGroupIds()])
  const report: string[] = []
  for (const mode of CATALOG_MODES) {
    const unseen = (stored.workspaces?.[mode]?.groups ?? []).filter((g) => g.id && !known.has(g.id))
    const hydrated = hydrateShareableGroups(unseen, { heroes: heroes.value, skills: skills.value }, report)
    workspaces[mode].groups.push(...hydrated.map((g) => ({ ...g, id: g.id as string })))
  }
  if (report.length > 0) healingReport.value = Array.from(new Set(report))
}

// Local autosave ---------------------------------------------------------

// Per-save values: two blobs equal apart from these hold the same user data.
const VOLATILE_BLOB_KEYS: ReadonlySet<string> = new Set(['gen', 'saved_at', 'device_id', 'updated_at'])

const blobContentKey = (blob: ShareableData): string => stableStringify(blob, VOLATILE_BLOB_KEYS)

const matchesStoredBlob = (blob: ShareableData): boolean => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw !== null && blobContentKey(JSON.parse(raw) as ShareableData) === blobContentKey(blob)
  } catch {
    return false
  }
}

// `force` is for decision paths, which must re-arm the cloud push even when
// the local content did not change.
const writeBlobToStorage = (force = false): void => {
  if (!force && Date.now() < suppressWritesUntil) {
    // Reactive echo from a recent applyBlobToLiveState (cross-tab message,
    // merge / conflict resolution). The window expires on its own — no need
    // to clear it here.
    return
  }
  // Applying a blob from a sibling tab fires the deep watcher. Saving that
  // echo would bump gen and broadcast, so the two tabs would keep waking each
  // other forever, with each round re-arming the cloud push.
  try {
    const unseen = storedBlobIsUnseen()
    if (unseen && !force) adoptUnseenSiblingGroups()
    if (!force && matchesStoredBlob(buildBlob(false))) {
      // Same content as an unseen save: this tab already holds all of it.
      if (unseen) lastSeenBlobRaw = readStoredRaw()
      return
    }
    if (unseen) missedSiblingSave = true
    const blob = buildBlob()
    const raw = JSON.stringify(blob)
    localStorage.setItem(STORAGE_KEY, raw)
    lastSeenBlobRaw = raw
    noteRemovedGroups()
    try { localStorage.removeItem(LEGACY_STORAGE_KEY) } catch { /* swallow */ }
    bc?.postMessage({
      type: 'saved',
      gen: blob.gen,
      device_id: blob.device_id,
    })
    // Cloud push uses a longer debounce so PostgREST writes scale to user
    // pause cadence, not edit-frame rate.
    scheduleCloudPush(blob)
  } catch (e) {
    // localStorage can throw on quota exceeded / private-browsing-disabled.
    // Don't crash the UI — surface a console warning. The next save attempt
    // re-tries on its own.
    console.warn('[autosave] write failed:', e)
  }
}

// A sibling saved while a dialog is open: wait for the dialog, so the save can
// keep that sibling's new groups instead of overwriting them.
const runScheduledWrite = (): void => {
  debounceHandle = null
  if (storedBlobIsUnseen() && siblingUpdatesBlocked()) {
    scheduleWrite()
    return
  }
  writeBlobToStorage()
}

const scheduleWrite = (): void => {
  if (!autosaveEnabled) return
  if (debounceHandle != null) clearTimeout(debounceHandle)
  debounceHandle = window.setTimeout(runScheduledWrite, LOCAL_DEBOUNCE_MS)
}

// Public: synchronously persist the current in-memory state to localStorage,
// bypassing the debounce window and the suppress guard. Called after every
// "user-meaningful" decision (merge resolution, conflict resolution, signout)
// so a F5 / logout / browser close that follows immediately does not lose
// the just-applied state. The reactive watcher's debounced write is already
// suppressed by these decision paths (to prevent a redundant write of state
// we're about to apply); without this explicit flush, the write never
// happens and localStorage stays frozen at the pre-decision state.
//
// Restore first: non-lineup routes never mount LineupBuilder, so workspaces
// may still be module-init defaults. Writing those would overwrite saved 編組.
const flushLocalAutosave = (): void => {
  restoreFromLocalStorage()
  seedHeldGroups()
  if (debounceHandle != null) {
    clearTimeout(debounceHandle)
    debounceHandle = null
  }
  suppressWritesUntil = 0
  writeBlobToStorage(true)
}

// Persist an in-flight debounced write now. Unlike flushLocalAutosave this
// does not restore-from-disk first (that latch is for routes that never
// mounted LineupBuilder) and is a no-op when nothing is pending — used by
// pagehide so F5 / tab discard within the 800ms window does not lose edits.
const flushPendingDebouncedWrite = (): void => {
  if (!autosaveEnabled) return
  if (debounceHandle == null) return
  clearTimeout(debounceHandle)
  debounceHandle = null
  suppressWritesUntil = 0
  writeBlobToStorage()
}

// Apply the blob currently in localStorage back into state. Used by the
// cross-tab listener — when another tab saves, we re-read and reconcile.
const applyBlobFromStorage = (): void => {
  try {
    const raw = readStoredRaw()
    if (!raw) return
    const blob = JSON.parse(raw) as ShareableData
    applyBlobToLiveState(blob)
    localGen = typeof blob.gen === 'number' ? blob.gen : localGen
    lastSeenBlobRaw = raw
    missedSiblingSave = false
    heldGroupIds = liveGroupIds()
  } catch (e) {
    console.warn('[autosave] cross-tab reconcile failed:', e)
  }
}

// Cloud sync -------------------------------------------------------------

// Tracks the most recent blob queued for cloud push. Captured here (instead
// of only inside the setTimeout closure) so flushPendingCloudPush() can
// cancel the debounce and synchronously fire the same blob before the user's
// auth token gets invalidated by signOut.
let pendingCloudBlob: ShareableData | null = null

const scheduleCloudPush = (blob: ShareableData): void => {
  if (!cloudSyncEnabled.value) return
  const { isLoggedIn } = useAuth()
  if (!isLoggedIn.value) return
  // While the merge dialog is up, we haven't agreed on what cloud state
  // should look like — suppress pushes until the user resolves it.
  // The same holds after "稍後再決定", until the user comes back to it.
  if (cloudMerge.value || cloudMergeDeferred.value) return
  // While a conflict is unresolved, stop pushing to avoid clobbering the
  // server row before the user has decided. The conflict dialog's resolvers
  // re-enable by clearing cloudConflict.
  if (cloudStatus.value === 'conflict') return
  pendingCloudBlob = blob
  // Bootstrap-not-yet-complete guard: keep the latest blob in
  // pendingCloudBlob but don't arm the debounce. Without this guard, a
  // push that fires during the listMyLineupGroups await sees an empty
  // cloudGroupsByClientId map, takes the INSERT branch for every group,
  // and 409s against existing cloud rows. markBootstrapped() reschedules
  // pendingCloudBlob the instant bootstrap completes — pushes are queued,
  // never dropped.
  if (!cloudBootstrapped) return
  if (cloudDebounceHandle != null) clearTimeout(cloudDebounceHandle)
  cloudDebounceHandle = window.setTimeout(() => {
    const b = pendingCloudBlob
    pendingCloudBlob = null
    cloudDebounceHandle = null
    if (b) void pushBlobToCloud(b)
  }, CLOUD_DEBOUNCE_MS)
}

// Flip the bootstrap latch and flush any push that was queued during the
// async bootstrap window. Called from every exit point of
// tryBootstrapCloudSync (including the merge dialog resolvers) so the
// pendingCloudBlob captured by scheduleCloudPush's guard never silently
// sits forever.
const markBootstrapped = (): void => {
  cloudBootstrapped = true
  bootstrapInFlight = false
  if (pendingCloudBlob) {
    const blob = pendingCloudBlob
    pendingCloudBlob = null
    scheduleCloudPush(blob)
  }
}

// Public: 全部重置 bumped the generation so an in-flight list cannot apply
// stale cloud rows over the wipe. skipCloudHydrate also blocks silent
// cloud→local on a bootstrap that starts after the wipe in this session.
// While a merge is deferred the wipe says nothing about the cloud rows, so it
// must not arm the path that deletes them; the 2x2 decides when the merge resumes.
const noteUserWipe = (): void => {
  bootstrapGeneration += 1
  if (!cloudMergeDeferred.value) skipCloudHydrate = true
}

const cancelPendingCloudPush = (): void => {
  if (cloudDebounceHandle != null) {
    clearTimeout(cloudDebounceHandle)
    cloudDebounceHandle = null
  }
  pendingCloudBlob = null
}

const rowContentHash = (r: CloudLineupGroup): string => groupContentHash(r.name, r.teams)

// Remember a row we just read or wrote. Without a hash the next push PATCHes it.
const recordCloudRow = (clientId: string, row: CloudLineupGroup, contentHash?: string): void => {
  cloudGroupsByClientId.set(clientId, {
    cloudId: row.id,
    serverUpdatedAt: row.updated_at,
    contentHash,
    sortOrder: row.sort_order,
  })
}

// For the paths where the user asked for the cloud to match local (wipe,
// keep-local): rows just listed that local does not hold are to go.
const markAbsentRowsRemoved = (): void => {
  const live = liveGroupIds()
  cloudGroupsByClientId.forEach((meta, clientId) => {
    if (!live.has(clientId)) meta.removed = true
  })
}

// After a pull: hash what local now serializes to, not what the row holds. If
// the two differ (a key this client does not know, a hero it cannot resolve),
// reading must not by itself rewrite the row. A later edit to the group still will.
const recordLiveHashes = (onlyClientId?: string): void => {
  shareableGroupsInBlob(buildBlob(false)).forEach((g, i) => {
    const meta = g.id ? cloudGroupsByClientId.get(g.id) : undefined
    if (!meta || (onlyClientId && g.id !== onlyClientId)) return
    meta.contentHash = groupContentHash(g.name, g.teams)
    meta.sortOrder = i
  })
}

// Replace cloudGroupsByClientId with a fresh snapshot from cloud. Used by
// keep-local when a row that survived its delete collided on the partial unique
// index and is missing from the bulk result. The user chose to overwrite the cloud, so these rows get no hash and the next push PATCHes them.
const hydrateMapFromCloud = async (): Promise<void> => {
  try {
    const rows = await listMyLineupGroups()
    cloudGroupsByClientId.clear()
    for (const r of rows) recordCloudRow(r.client_id ?? r.id, r)
  } catch (e) {
    console.warn('[cloud-sync] hydrate map from cloud failed:', e)
  }
}

// Public: cancel any debounced cloud push and fire it immediately. Callers
// (signOut handler) await this so the user's last edits make it to cloud
// BEFORE the auth token is invalidated. No-op when nothing is pending or
// when the user isn't logged in.
const flushPendingCloudPush = async (): Promise<void> => {
  // Bootstrap still owns the map — leave pendingCloudBlob so the wipe
  // branch / markBootstrapped can push with a seeded map + stale-delete.
  if (!cloudBootstrapped) return
  if (cloudDebounceHandle != null) {
    clearTimeout(cloudDebounceHandle)
    cloudDebounceHandle = null
  }
  const b = pendingCloudBlob
  pendingCloudBlob = null
  if (!b) return
  const { isLoggedIn } = useAuth()
  if (!isLoggedIn.value) return
  if (!cloudSyncEnabled.value) return
  try {
    await pushBlobToCloud(b)
  } catch (e) {
    // Don't block signout on a failed flush — local data survives, and the
    // user already pressed the logout button.
    console.warn('[cloud-sync] flush-on-signout push failed:', e)
  }
}

type PushableGroup = ShareableGroup & { id: string }
type PushStep = 'next' | 'halt'

// Surface the conflict to the user; halt the rest of the push so we don't
// compound the divergence.
const haltOnConflict = (localGroupId: string, serverRow: CloudLineupGroup): PushStep => {
  cloudConflict.value = { localGroupId, serverRow }
  cloudStatus.value = 'conflict'
  return 'halt'
}

// Local serialization round-trips through hydration, so a row written in an older
// shape can differ from the local copy of the same data. Compare after the same
// round trip. A row with an entry this catalog cannot resolve never matches: the
// round trip dropped that entry, and it is not this client's to discard.
const rowMatchesLocal = (g: PushableGroup, row: CloudLineupGroup): boolean => {
  const localHash = groupContentHash(g.name, g.teams)
  if (rowContentHash(row) === localHash) return true
  const { heroes, skills } = useData()
  const deps = { heroes: heroes.value, skills: skills.value }
  const report: string[] = []
  const [hydrated] = hydrateShareableGroups([rowToShareableGroup(row)], deps, report)
  if (report.length > 0) return false
  const teams = hydrated.teams.map((t) => makeSerializer(deps).serializeLineup(t))
  return groupContentHash(hydrated.name, teams) === localHash
}

// The INSERT found an existing row, so nothing of ours was written. Same content
// is fine. A row with no teams has nothing to lose, so local may fill it.
// Anything else is the user's decision: taking the row's updated_at as our lock
// would let the next push overwrite it with no dialog.
const adoptExistingRow = (g: PushableGroup, row: CloudLineupGroup, sortOrder: number): Promise<PushStep> | PushStep => {
  if (rowMatchesLocal(g, row)) {
    recordCloudRow(g.id, row, groupContentHash(g.name, g.teams))
    return 'next'
  }
  if (!row.teams.every(isEmptyShareableLineup)) return haltOnConflict(g.id, row)
  recordCloudRow(g.id, row)
  return patchGroup(g, sortOrder)
}

// createLineupGroup falls back to GET-by-client_id on a duplicate, so a stale
// local map (cloud row exists but we don't know about it) resolves to a row
// reference, whichever way the server reports the collision.
const insertGroup = async (g: PushableGroup, sortOrder: number): Promise<PushStep> => {
  const { row, adopted } = await createLineupGroup({
    client_id: g.id,
    name: g.name,
    teams: g.teams,
    sort_order: sortOrder,
  })
  if (adopted) return adoptExistingRow(g, row, sortOrder)
  recordCloudRow(g.id, row, rowContentHash(row))
  return 'next'
}

const patchGroup = async (g: PushableGroup, sortOrder: number): Promise<PushStep> => {
  const meta = cloudGroupsByClientId.get(g.id)
  if (!meta || meta.rowGone) {
    cloudGroupsByClientId.delete(g.id)
    return insertGroup(g, sortOrder)
  }
  const contentHash = groupContentHash(g.name, g.teams)
  const result = await patchLineupGroupWithLock(meta.cloudId, meta.serverUpdatedAt, {
    name: g.name,
    teams: g.teams,
    sort_order: sortOrder,
  })
  switch (result.kind) {
    case 'ok':
      recordCloudRow(g.id, result.row, contentHash)
      return 'next'
    case 'conflict':
      return haltOnConflict(g.id, result.serverRow)
    case 'deleted':
      // Another client deleted the row. With the content unchanged (this PATCH
      // was only a position shift) nothing is at stake: respect the delete in the
      // cloud and keep the local copy; a later edit uploads it. Otherwise upload
      // now, including when old meta has no hash and an edit cannot be ruled out:
      // an unwanted group can be deleted a second time, but lost edits cannot be
      // recovered.
      if (meta.contentHash === contentHash) {
        cloudGroupsByClientId.set(g.id, { ...meta, rowGone: true })
        return 'next'
      }
      cloudGroupsByClientId.delete(g.id)
      return insertGroup(g, sortOrder)
    default:
      // Next edit retries via the debounce.
      console.warn('[cloud-sync] patch failed:', result.message)
      cloudStatus.value = 'error'
      return 'halt'
  }
}

const pushGroup = async (g: PushableGroup, sortOrder: number): Promise<PushStep> => {
  const meta = cloudGroupsByClientId.get(g.id)
  if (meta?.contentHash === groupContentHash(g.name, g.teams)) {
    if (meta.rowGone || meta.sortOrder === sortOrder) return 'next'
  }
  return patchGroup(g, sortOrder)
}

// Delete cloud rows the user removed locally. Being absent from the local list
// is not enough: a tab can learn of a row from stored meta without ever having
// held the group, because a sibling created it. Only run when the local groups
// list is the source of truth — i.e. cloud sync is enabled and we've finished
// the bootstrap.
const deleteStaleRows = async (liveGroups: ShareableGroup[]): Promise<void> => {
  if (!cloudBootstrapped) return
  const liveIds = new Set(liveGroups.map((g) => g.id))
  const stale = [...cloudGroupsByClientId.entries()]
    .filter(([clientId, meta]) => meta.removed && !liveIds.has(clientId))
  for (const [clientId, meta] of stale) {
    try {
      await deleteLineupGroup(meta.cloudId)
      cloudGroupsByClientId.delete(clientId)
    } catch (e) {
      console.warn('[cloud-sync] delete stale row failed:', e)
    }
  }
}

const pushBlobToCloud = async (blob: ShareableData): Promise<void> => {
  if (!cloudSyncEnabled.value || cloudMergeDeferred.value) return
  const { isLoggedIn } = useAuth()
  if (!isLoggedIn.value) return
  const groupsToPush = shareableGroupsInBlob(blob)
  if (groupsToPush.length === 0) return

  cloudStatus.value = 'syncing'
  reloadCloudMetaFromStorage()
  try {
    for (let i = 0; i < groupsToPush.length; i++) {
      const g = groupsToPush[i]
      if (!g.id) continue // shouldn't happen for v4 blobs; defensive guard
      if (await pushGroup(g as PushableGroup, i) === 'halt') return
    }
    await deleteStaleRows(groupsToPush)
    cloudStatus.value = 'idle'
  } catch (e) {
    // Network / auth-expired failures — don't retry in a loop, the next
    // edit will reschedule. Status surface drives any user-visible UI.
    console.warn('[cloud-sync]', e)
    cloudStatus.value = 'offline'
  } finally {
    // Every exit, including a halt: rows already written have new updated_at
    // values, and a reload must not take its own writes for another client's.
    syncCloudMetaToStorage()
  }
}

// Apply cloud rows to local state. Used by the 2x2 silent path (local
// empty, cloud non-empty) and by "use cloud" in the conflict / merge dialogs.
const applyCloudRowsToLocal = (rows: CloudLineupGroup[]): void => {
  const blob = cloudRowsToBlob(rows)
  // Suppress the autosave echo from the reactive replaceGroups that follows.
  // Without this the local watcher would fire and immediately push the same
  // data back to cloud (harmless but wasteful) before the meta map is set up.
  suppressWritesUntil = Date.now() + SUPPRESS_WINDOW_MS
  applyBlobToLiveState(blob)
  // Rebuild the client_id ↔ cloudId meta map from the rows we just loaded.
  cloudGroupsByClientId.clear()
  for (const r of rows) recordCloudRow(r.client_id ?? r.id, r)
  recordLiveHashes()
  heldGroupIds = liveGroupIds()
}

// Backup-share-link safety net — used by the discard-side of the merge dialog
// so the user never silently loses data. Returns the slug or null on failure.
const createBackupShareLink = async (blob: ShareableData): Promise<string | null> => {
  try {
    return await createShare(blob, { kind: 'group', displayName: `編組備份 ${new Date().toLocaleString('zh-TW')}` })
  } catch (e) {
    console.warn('[cloud-sync] backup share failed:', e)
    return null
  }
}

// Public: kick off the anon→signed-in handoff. Idempotent — guarded by
// cloudBootstrapped. Called from LineupBuilder.vue's onMounted after the
// other restore paths have settled, and from the post-OAuth callback hook.
const tryBootstrapCloudSync = async (): Promise<void> => {
  if (cloudBootstrapped || bootstrapInFlight) return
  const { isLoggedIn, user } = useAuth()
  if (!isLoggedIn.value) return
  if (!cloudSyncEnabled.value) {
    markBootstrapped() // remember so toggling sync back on doesn't re-prompt
    return
  }
  const userId = user.value?.id
  if (!userId) return // shouldn't happen given isLoggedIn — defensive

  // Hydrate still-pristine workspaces first — setCloudSyncEnabled can
  // re-bootstrap without LineupBuilder ever mounting.
  restoreFromLocalStorage()
  seedHeldGroups()

  // Fast-path emptiness is sampled NOW (sync). The 2x2 re-samples after
  // the list await so a wipe/edit during the fetch is not decided on a
  // stale empty flag. We read groups directly (not via buildBlob) so the
  // read-only decision doesn't pollute the cross-tab gen counter.
  const { workspaces } = useGroups()
  const localActuallyEmpty = CATALOG_MODES.every((m) =>
    isEmptyGroupSet(workspaces[m].groups),
  )

  // Fast path: this device + user has been bootstrapped before AND local
  // still has actual content AND every non-empty workspace overlaps the
  // persisted meta map. Restore the cloud meta so subsequent PATCHes carry
  // the optimistic-lock preconditions we last observed; skip the 2x2 /
  // merge dialog entirely. If a competing device pushed while we were
  // offline, the next push hits a precondition mismatch and surfaces the
  // conflict dialog naturally.
  //
  // We REQUIRE non-empty local for the fast path. With empty local, the
  // "local == cloud" invariant the fast path assumes is broken: either the
  // user wiped local (reset, browser data clear) while signed out, OR
  // localStorage never got the post-cloud-fetch write. In either case we
  // must fall through to the full 2x2, otherwise the empty local would
  // silently overwrite cloud on the next autosave push.
  //
  // A workspace whose live ids are disjoint from the persisted map (v5
  // share restore mints ids in the active mode only) is a 2x2/merge case
  // — otherwise the other mode's overlap would skip the prompt and the
  // next push stale-deletes the replaced mode's cloud 編組. Genuine
  // per-group deletes still overlap via remaining ids, so stale-delete
  // after a real bootstrap is unchanged.
  const persisted = loadPersistedCloudMeta(userId)
  if (persisted && !localActuallyEmpty) {
    const everyNonEmptyOverlaps = CATALOG_MODES.every((m) => {
      const groups = workspaces[m].groups
      if (isEmptyGroupSet(groups)) return true
      return groups.some((g) => Boolean(g.id && persisted[g.id]))
    })
    if (everyNonEmptyOverlaps) {
      cloudGroupsByClientId.clear()
      for (const [clientId, m] of Object.entries(persisted)) {
        cloudGroupsByClientId.set(clientId, m)
      }
      cloudStatus.value = 'idle'
      markBootstrapped()
      return
    }
  }

  // Cold start (or local-wiped re-bootstrap). Run the 2x2.
  const gen = bootstrapGeneration
  bootstrapFlightGen = gen
  bootstrapInFlight = true
  cloudStatus.value = 'syncing'
  let cloudRows: CloudLineupGroup[]
  try {
    cloudRows = await listMyLineupGroups()
  } catch (e) {
    console.warn('[cloud-sync] bootstrap list failed:', e)
    cloudStatus.value = 'offline'
    if (bootstrapFlightGen === gen) bootstrapInFlight = false
    // Leave cloudBootstrapped false so a later `persisted` can retry.
    return
  }

  if (gen !== bootstrapGeneration && !skipCloudHydrate) {
    // Stale flight (logout / disable). Do not latch — next sign-in must 2x2.
    // Drop the mutex only if this flight still owns it; a newer sign-in
    // may have already set inFlight for a newer gen.
    cloudStatus.value = 'idle'
    if (bootstrapFlightGen === gen) bootstrapInFlight = false
    return
  }

  const localEmptyNow = CATALOG_MODES.every((m) =>
    isEmptyGroupSet(workspaces[m].groups),
  )

  // Empty-check the cloud side: a cloud row with only empty teams counts
  // as empty — that data is dead weight and shouldn't force a merge dialog.
  const cloudActuallyEmpty = cloudRows.every(
    (r) => r.teams.every(isEmptyShareableLineup),
  )

  if (skipCloudHydrate) {
    // User wiped this session (possibly during the fetch). Keep local;
    // seed the meta map from the list we already have so the empty push
    // can stale-delete old cloud rows this turn (not the 1800ms debounce).
    cloudGroupsByClientId.clear()
    for (const r of cloudRows) recordCloudRow(r.client_id ?? r.id, r)
    markAbsentRowsRemoved()
    cloudStatus.value = 'idle'
    syncCloudMetaToStorage()
    // Latch the map before the wipe push so stale-delete is allowed, but
    // do not markBootstrapped yet — that would flush a parallel second push.
    cloudBootstrapped = true
    const blob = buildBlob()  // live state, includes hero added during the wait
    pendingCloudBlob = null
    try {
      await pushBlobToCloud(blob)
    } finally {
      // Flushes nothing if pending stayed null; still drops inFlight.
      // If user edits scheduled a pending during the await, flush after.
      markBootstrapped()
    }
    return
  }

  if (localEmptyNow && cloudActuallyEmpty) {
    // Both empty — silent no-op. Persist an empty meta so reloads take the
    // fast path above.
    cloudStatus.value = 'idle'
    syncCloudMetaToStorage()
    markBootstrapped()
    return
  }

  if (localEmptyNow && !cloudActuallyEmpty) {
    // Silent apply: cloud → local. applyCloudRowsToLocal populates the meta
    // map; persist it so the next reload takes the fast path. flushLocalAutosave
    // also writes the freshly-applied groups to localStorage immediately —
    // without it, a F5 within 800ms would re-read the pre-apply (empty) blob.
    applyCloudRowsToLocal(cloudRows)
    cloudStatus.value = 'idle'
    syncCloudMetaToStorage()
    flushLocalAutosave()
    markBootstrapped()
    return
  }

  if (!localEmptyNow && cloudActuallyEmpty) {
    // Silent upload: local → cloud. buildBlob here is the actual write — it
    // owns the gen bump because we'll be persisting these groups to cloud.
    const localBlob = buildBlob()
    const localInputs = shareableGroupsInBlob(localBlob).map((g, i) => ({
      client_id: g.id,
      name: g.name,
      teams: g.teams,
      sort_order: i,
    }))
    try {
      const created = await bulkCreateLineupGroups(localInputs)
      for (const r of created) recordCloudRow(r.client_id ?? r.id, r, rowContentHash(r))
      cloudStatus.value = 'idle'
      syncCloudMetaToStorage()
      markBootstrapped()
      // Rows that collided with an existing row are missing from the result.
      // Push again so those groups go through the INSERT path, which compares
      // content before it takes over an existing row.
      // An edit made during the upload is newer and already queued.
      if (created.length < localInputs.length) scheduleCloudPush(pendingCloudBlob ?? localBlob)
    } catch (e) {
      console.warn('[cloud-sync] bulk upload failed:', e)
      cloudStatus.value = 'offline'
      if (bootstrapFlightGen === gen) bootstrapInFlight = false
    }
    return
  }

  // Both non-empty — needs explicit user choice. Dialog resolver handlers
  // call syncCloudMetaToStorage on success. ctx snapshot only — the actual
  // writes happen inside the resolveMerge* handlers and bump gen there.
  const localBlob = buildBlob(false)
  cloudMerge.value = { localBlob, cloudRows }
  cloudStatus.value = 'idle'
  if (bootstrapFlightGen === gen) bootstrapInFlight = false
}

// Merge-dialog resolutions ---------------------------------------------

export interface MergeResolutionResult {
  kind: 'keep-cloud' | 'keep-local' | 'append' | 'cancel'
  backupSlug?: string | null
}

const resolveMergeKeepCloud = async (): Promise<MergeResolutionResult> => {
  const ctx = cloudMerge.value
  if (!ctx) return { kind: 'cancel' }
  cloudStatus.value = 'syncing'

  // Safety net: stash the local data as a backup share link so the user
  // can recover if they realize this was the wrong choice.
  const backupSlug = await createBackupShareLink(ctx.localBlob)

  applyCloudRowsToLocal(ctx.cloudRows)
  cloudMerge.value = null
  cloudStatus.value = 'idle'
  syncCloudMetaToStorage()
  flushLocalAutosave()
  markBootstrapped()
  return { kind: 'keep-cloud', backupSlug }
}

const resolveMergeKeepLocal = async (): Promise<MergeResolutionResult> => {
  const ctx = cloudMerge.value
  if (!ctx) return { kind: 'cancel' }
  cloudStatus.value = 'syncing'

  // Backup the cloud state as a share link before destroying it.
  const cloudBlob = cloudRowsToBlob(ctx.cloudRows)
  const backupSlug = await createBackupShareLink(cloudBlob)

  // Snapshot the local state RIGHT NOW — same rationale as
  // resolveMergeAppend: the dialog can sit open for minutes; the user's
  // intent on "keep local" is to push their CURRENT local state to cloud,
  // not the bootstrap-time snapshot in ctx.localBlob.
  const freshLocalBlob = buildBlob()

  // Delete all cloud rows, then bulk-create from local.
  try {
    for (const r of ctx.cloudRows) {
      try {
        await deleteLineupGroup(r.id)
      } catch (e) {
        console.warn('[cloud-sync] delete row during overwrite failed:', e)
      }
    }
    const localInputs = shareableGroupsInBlob(freshLocalBlob).map((g, i) => ({
      client_id: g.id,
      name: g.name,
      teams: g.teams,
      sort_order: i,
    }))
    const created = await bulkCreateLineupGroups(localInputs)
    cloudGroupsByClientId.clear()
    for (const r of created) recordCloudRow(r.client_id ?? r.id, r, rowContentHash(r))
    // Defensive: deleteLineupGroup above is best-effort (errors are swallowed),
    // so a stray surviving cloud row could collide with our insert and be
    // missing from the result. Re-list cloud to fill any missing meta.
    if (created.length < localInputs.length) {
      await hydrateMapFromCloud()
      markAbsentRowsRemoved()
    }
    cloudMerge.value = null
    cloudStatus.value = 'idle'
    syncCloudMetaToStorage()
    flushLocalAutosave()
    markBootstrapped()
    return { kind: 'keep-local', backupSlug }
  } catch (e) {
    console.warn('[cloud-sync] keep-local failed:', e)
    cloudStatus.value = 'error'
    return { kind: 'cancel' }
  }
}

// Append cloud groups after local, per workspace. Capped at 20 per mode so
// merging never drops the other workspace to make room.
const APPEND_MAX_TOTAL = 20

const appendWorkspaceGroups = (
  localGroups: ShareableGroup[],
  cloudGroups: ShareableGroup[],
): { merged: ShareableGroup[]; adopted: ShareableGroup[] } => {
  const capacity = Math.max(0, APPEND_MAX_TOTAL - localGroups.length)
  const adopted = [...cloudGroups]
    .sort((a, b) => {
      const at = a.updated_at ?? ''
      const bt = b.updated_at ?? ''
      return at < bt ? 1 : at > bt ? -1 : 0
    })
    .slice(0, capacity)
  const cloudNames = new Set(adopted.map((g) => g.name))
  const localRenamed = localGroups.map((g) =>
    cloudNames.has(g.name) ? { ...g, name: `本地-${g.name}` } : g,
  )
  return { merged: [...localRenamed, ...adopted], adopted }
}

const resolveMergeAppend = async (): Promise<MergeResolutionResult> => {
  const ctx = cloudMerge.value
  if (!ctx) return { kind: 'cancel' }
  cloudStatus.value = 'syncing'

  // Snapshot the local state RIGHT NOW (not at bootstrap time). The dialog
  // can sit open for minutes; any local edits the user made while the dialog
  // was visible would be lost if we used ctx.localBlob (the bootstrap-time
  // snapshot). ctx.localBlob is still kept as the backup-share-link target.
  const freshLocalBlob = buildBlob()
  // Split by id prefix only — do NOT run the v4 "copy into both" migration
  // here. Unprefixed cloud rows belong to 庫存; duplicating them into 自由
  // would clone teams the local v5 workspace already has.
  const cloudSplit = splitCloudRowsByWorkspace(ctx.cloudRows)
  const adopted: ShareableGroup[] = []
  const mergedWorkspaces = {} as NonNullable<ShareableData['workspaces']>
  for (const mode of CATALOG_MODES) {
    const localGroups = freshLocalBlob.workspaces?.[mode]?.groups ?? []
    const localIds = new Set(localGroups.map((g) => g.id))
    const cloudGroups = cloudSplit[mode].filter((g) => !localIds.has(g.id))
    const result = appendWorkspaceGroups(localGroups, cloudGroups)
    adopted.push(...result.adopted)
    mergedWorkspaces[mode] = {
      active_group_index: freshLocalBlob.workspaces?.[mode]?.active_group_index ?? 0,
      active_team_index: freshLocalBlob.workspaces?.[mode]?.active_team_index,
      groups: result.merged,
    }
  }

  const merged: ShareableData = {
    v: 5,
    inv_h: freshLocalBlob.inv_h,
    inv_s: freshLocalBlob.inv_s,
    workspaces: mergedWorkspaces,
  }

  suppressWritesUntil = Date.now() + SUPPRESS_WINDOW_MS
  applyBlobToLiveState(merged)

  // Seed the meta map for the cloud rows we just adopted. They now sit after
  // the local groups, so they get no hash and the next push rewrites sort_order.
  // The local ones will INSERT on the next pushBlobToCloud (no meta entry →
  // createLineupGroup path). A local group whose id already exists in the cloud
  // was filtered out above, so that INSERT raises a conflict if content differs.
  // Match by client_id against the original cloud rows.
  const adoptedIds = new Set(adopted.map((g) => g.id))
  for (const r of ctx.cloudRows) {
    const clientId = r.client_id ?? r.id
    if (adoptedIds.has(clientId)) recordCloudRow(clientId, r)
  }
  cloudMerge.value = null
  cloudStatus.value = 'idle'
  syncCloudMetaToStorage()
  flushLocalAutosave()
  markBootstrapped()
  return { kind: 'append' }
}

const resolveMergeCancel = (): void => {
  cloudMerge.value = null
  // No push until the user decides. Nothing is written to the meta either, so
  // a reload takes the same path back to this dialog.
  cloudMergeDeferred.value = true
  cancelPendingCloudPush()
  // Mark bootstrapped so token refresh / other `persisted` events in THIS
  // session don't re-trigger the dialog. Next page reload still re-runs
  // bootstrap (cloudBootstrapped is module-state, not persisted), giving
  // the user a fresh prompt on a new session.
  cloudStatus.value = 'idle'
  markBootstrapped()
}

// Public: come back to a deferred merge. Re-runs the 2x2 against a fresh list,
// since the cloud and local may both have moved since the dialog closed.
const reopenDeferredMerge = (): void => {
  if (!cloudMergeDeferred.value) return
  cloudMergeDeferred.value = false
  cloudBootstrapped = false
  void tryBootstrapCloudSync()
}

// Conflict-dialog resolutions ------------------------------------------

const resolveConflictUseServer = async (): Promise<void> => {
  const ctx = cloudConflict.value
  if (!ctx) return
  cloudStatus.value = 'syncing'
  reloadCloudMetaFromStorage()

  // Snapshot BOTH workspaces and swap the one conflicting group so the
  // other mode is not dropped. applyBlobToLiveState is the only sanctioned
  // mutation path that runs the healing pass and triggers the useLineups
  // watcher cleanly.
  const blob = buildBlob(false)
  const replacement: ShareableGroup = {
    id: ctx.serverRow.client_id ?? ctx.serverRow.id,
    name: ctx.serverRow.name,
    updated_at: ctx.serverRow.updated_at,
    teams: ctx.serverRow.teams,
  }
  for (const mode of CATALOG_MODES) {
    const groups = blob.workspaces?.[mode]?.groups
    if (!groups) continue
    const idx = groups.findIndex((g) => g.id === ctx.localGroupId)
    if (idx >= 0) groups[idx] = replacement
  }

  suppressWritesUntil = Date.now() + SUPPRESS_WINDOW_MS
  applyBlobToLiveState(blob)

  // Refresh meta for the swapped group so the next push uses the freshly
  // observed updated_at as its precondition.
  const clientId = ctx.serverRow.client_id ?? ctx.serverRow.id
  recordCloudRow(clientId, ctx.serverRow)
  recordLiveHashes(clientId)
  cloudConflict.value = null
  cloudStatus.value = 'idle'
  syncCloudMetaToStorage()
  if (storedBlobIsUnseen()) adoptUnseenSiblingGroups()
  flushLocalAutosave()
}

const resolveConflictForceOverwrite = async (): Promise<void> => {
  const ctx = cloudConflict.value
  if (!ctx) return
  cloudStatus.value = 'syncing'

  // Find the current local group (post-edit) and push it without the lock.
  const { findGroupById } = useGroups()
  const localGroup = findGroupById(ctx.localGroupId)
  if (!localGroup) {
    cloudConflict.value = null
    cloudStatus.value = 'idle'
    return
  }
  const { heroes, skills } = useData()
  const serializer = makeSerializer({ heroes: heroes.value, skills: skills.value })
  const teams = localGroup.teams.map((t) => serializer.serializeLineup(t))
  reloadCloudMetaFromStorage()
  try {
    const row = await patchLineupGroupForce(ctx.serverRow.id, { name: localGroup.name, teams })
    // A row deleted in the meantime has no meta, so the push below inserts it.
    if (row) recordCloudRow(ctx.localGroupId, row, groupContentHash(localGroup.name, teams))
    else cloudGroupsByClientId.delete(ctx.localGroupId)
    cloudConflict.value = null
    cloudStatus.value = 'idle'
    syncCloudMetaToStorage()
    // The conflict halted the push that found it; finish the other groups.
    scheduleCloudPush(buildBlob(false))
  } catch (e) {
    console.warn('[cloud-sync] force overwrite failed:', e)
    cloudStatus.value = 'error'
    throw e
  }
}

// Session only, as the dialog says: the stored preference is left alone, so the
// next load has sync on again and the conflict comes back on the next edit.
const resolveConflictDefer = (): void => {
  cloudConflict.value = null
  cloudSyncEnabled.value = false
  cloudStatus.value = 'idle'
}

// Manual toggle ---------------------------------------------------------

const setCloudSyncEnabled = (v: boolean): void => {
  cloudSyncEnabled.value = v
  persistCloudSyncPref(v)
  cloudMergeDeferred.value = false
  if (v) {
    // Turning sync on after a defer / fresh session — re-run bootstrap.
    cloudBootstrapped = false
    void tryBootstrapCloudSync()
  } else {
    // Turning sync off — drop the meta map so re-enabling later starts
    // from a clean slate. Also cancel any in-flight debounce and discard
    // the queued blob, so a re-enable doesn't resurrect a stale pre-disable
    // push and clobber cloud with old state. Mirrors the `expired` handler.
    // Bump generation so an in-flight 2x2 cannot apply; do not clear
    // bootstrapInFlight — the aborted continuation drops the mutex.
    bootstrapGeneration += 1
    cloudGroupsByClientId.clear()
    cloudBootstrapped = false
    cancelPendingCloudPush()
  }
}

// Lifecycle -------------------------------------------------------------

// Latch: only run cloud bootstrap from session events AFTER the host view's
// onMounted has finished its restore sequence (share-link, OAuth recovery,
// localStorage). Set to true by enableAutosave (the last thing onMounted
// does). Before that, session events queue intent but don't fire bootstrap
// — that prevents a race where a fast `persisted` event fires concurrently
// with restoreFromLocalStorage and pushes stale state to cloud.
let postMountReady = false

// Subscribe to auth events once at module load. signed-out / expired must
// disable cloud-sync state but NEVER touch localStorage — the user's local
// data has to survive sign-out per the brief.
onSessionEvent((e) => {
  if (e === 'expired' || e === 'signed-out') {
    bootstrapGeneration += 1
    skipCloudHydrate = false  // next sign-in may hydrate
    cloudGroupsByClientId.clear()
    cloudBootstrapped = false
    bootstrapInFlight = false
    cloudConflict.value = null
    cloudMerge.value = null
    cloudMergeDeferred.value = false
    missedSiblingSave = false
    cloudStatus.value = 'idle'
    // Invalidate persisted meta — once signed out, the "local == cloud"
    // invariant no longer holds (user can reset, edit, etc., off-line).
    // Forces the next sign-in through the full 2x2 instead of fast-path.
    clearPersistedCloudMeta()
    if (e === 'expired') {
      // Token is dead — drop any pending push instead of letting the
      // setTimeout tick fire it and 401 silently. (signed-out is already
      // covered by flushPendingCloudPush() in AppLayout's handler.)
      cancelPendingCloudPush()
    }
    // Don't flip cloudSyncEnabled — the user's preference survives a
    // session round trip. Next sign-in re-bootstraps.
  } else if (e === 'persisted') {
    // Post-OAuth callback fires this once the new token lands. If onMounted
    // has already finished, run bootstrap now (the user just signed in and
    // is sitting on the page); otherwise defer to enableAutosave's latch.
    if (postMountReady) void tryBootstrapCloudSync()
  }
})

// Public: attempt a restore from localStorage. Returns true if anything was
// restored. Once per session — a later pass would treat a post-wipe default
// as pristine and re-apply the pre-wipe blob. LineupBuilder restores first
// then overlays share/OAuth; the latch makes a later flushLocalAutosave a
// write-only so it cannot re-apply disk over the overlay. The pristine skip
// still fills only untouched workspaces if this runs after a partial hydrate.
let localRestoreAttempted = false

const restoreFromLocalStorage = (): boolean => {
  if (localRestoreAttempted) return false
  localRestoreAttempted = true

  const raw = readStoredRaw()
  lastSeenBlobRaw = raw
  if (!raw) return false

  let blob: ShareableData
  try {
    blob = JSON.parse(raw) as ShareableData
  } catch {
    return false
  }

  if (blob.v !== 4 && blob.v !== 5) return false

  const v5 = wrapV4AsV5(blob)
  const { isPristineWorkspace, replaceWorkspace } = useGroups()
  const { ownedHeroes, ownedSkills } = useInventory()
  const { heroes, skills } = useData()
  const deps = { heroes: heroes.value, skills: skills.value }
  const report: string[] = []
  let applied = false

  // Per-workspace: a share-link that filled 自由 must not block restoring
  // 庫存 from autosave, and vice versa.
  for (const mode of CATALOG_MODES) {
    if (!isPristineWorkspace(mode)) continue
    const ws = v5.workspaces?.[mode]
    if (!ws?.groups?.length) continue
    replaceWorkspace(mode, {
      groups: hydrateShareableGroups(ws.groups, deps, report),
      currentGroupIndex: ws.active_group_index,
      currentTeamIndex: ws.active_team_index,
    })
    applied = true
  }

  // Inventory is shared. Only fill it when the earlier path (share / OAuth)
  // left it empty — an inventory-only share already wrote owned*.
  if (ownedHeroes.value.length === 0 && ownedSkills.value.length === 0) {
    if (v5.inv_h || v5.inv_s || v5.inventory) {
      applyBlobToState(
        { v: 5, inv_h: v5.inv_h, inv_s: v5.inv_s, inventory: v5.inventory },
        buildApplyDeps(),
        { scope: 'active' },
      )
      applied = true
    }
  }

  if (report.length > 0) healingReport.value = Array.from(new Set(report))
  return applied
}

// Public: enable the autosave watcher + cross-tab listener. Idempotent.
// Also flips postMountReady so subsequent session events trigger bootstrap.
const enableAutosave = (): void => {
  if (autosaveEnabled) return
  autosaveEnabled = true
  postMountReady = true
  seedHeldGroups()

  const { workspaces } = useGroups()
  const { ownedHeroes, ownedSkills } = useInventory()

  watch(
    [workspaces, ownedHeroes, ownedSkills],
    scheduleWrite,
    { deep: true },
  )

  // BroadcastChannel may be unavailable in very old browsers — degrade
  // gracefully: autosave still works, just without cross-tab reconciliation.
  if (typeof BroadcastChannel === 'function') {
    bc = new BroadcastChannel(BROADCAST_CHANNEL_NAME)
    const ourDeviceId = getOrCreateDeviceId()
    bc.onmessage = (ev) => {
      const msg = ev.data as
        | { type: 'saved'; gen: number; device_id: string }
        | undefined
      if (!msg || msg.type !== 'saved') return
      if (msg.device_id !== ourDeviceId) return
      if (msg.gen <= localGen) return
      // While a merge / conflict / import dialog is open, ignore cross-tab
      // updates — the dialog's snapshot (capacity calc, hydrated teams,
      // local-name collision set) would diverge from live state mid-decision,
      // and resolving with the diverged snapshot would silently discard
      // edits made in the other tab.
      if (siblingUpdatesBlocked()) return
      suppressWritesUntil = Date.now() + SUPPRESS_WINDOW_MS
      applyBlobFromStorage()
      // The sibling's newer blob supersedes ours and it pushes that blob itself.
      // Pushing ours too would race its lock and raise a conflict with ourselves.
      cancelPendingCloudPush()
    }
  }

  // pagehide fires on F5, tab close, and mobile tab discard. beforeunload
  // is unreliable on mobile; visibilitychange-to-hidden is too aggressive
  // (app switch). Only flush when a debounce is actually armed.
  window.addEventListener('pagehide', flushPendingDebouncedWrite)
}

export interface UseGroupPersistence {
  // Phase A
  restoreFromLocalStorage: () => boolean
  enableAutosave: () => void
  snapshotForRecovery: () => void
  consumeRecovery: () => boolean
  healingReport: typeof healingReport
  // Phase C
  cloudSyncEnabled: typeof cloudSyncEnabled
  cloudStatus: typeof cloudStatus
  cloudConflict: typeof cloudConflict
  cloudMerge: typeof cloudMerge
  cloudMergeDeferred: typeof cloudMergeDeferred
  reopenDeferredMerge: () => void
  tryBootstrapCloudSync: () => Promise<void>
  noteUserWipe: () => void
  flushPendingCloudPush: () => Promise<void>
  flushLocalAutosave: () => void
  setCloudSyncEnabled: (v: boolean) => void
  resolveMergeKeepCloud: () => Promise<MergeResolutionResult>
  resolveMergeKeepLocal: () => Promise<MergeResolutionResult>
  resolveMergeAppend: () => Promise<MergeResolutionResult>
  resolveMergeCancel: () => void
  resolveConflictUseServer: () => Promise<void>
  resolveConflictForceOverwrite: () => Promise<void>
  resolveConflictDefer: () => void
}

export function useGroupPersistence(): UseGroupPersistence {
  return {
    restoreFromLocalStorage,
    enableAutosave,
    snapshotForRecovery,
    consumeRecovery,
    healingReport,
    cloudSyncEnabled,
    cloudStatus,
    cloudConflict,
    cloudMerge,
    cloudMergeDeferred,
    reopenDeferredMerge,
    tryBootstrapCloudSync,
    noteUserWipe,
    flushPendingCloudPush,
    flushLocalAutosave,
    setCloudSyncEnabled,
    resolveMergeKeepCloud,
    resolveMergeKeepLocal,
    resolveMergeAppend,
    resolveMergeCancel,
    resolveConflictUseServer,
    resolveConflictForceOverwrite,
    resolveConflictDefer,
  }
}
