export const TRANSPARENT_GIF = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

const RATE_RANGE_REGEX = /(\d+(?:\.\d+)?%?)\s*(?:->|to|→)\s*(\d+(?:\.\d+)?%?)/
export const formatRate = (rateStr: string | undefined, maxLevel: boolean): string => {
  if (!rateStr) return ''
  const match = rateStr.match(RATE_RANGE_REGEX)
  if (match) return maxLevel ? match[2] : match[1]
  return rateStr
}

export const getTraitColor = (rank: string): string => {
  // Balanced palette: same shade weight (50/300/700) across all tiers.
  switch (rank) {
    case 'S': return 'bg-yellow-50 border-yellow-300 text-yellow-700 font-bold'
    case 'A': return 'bg-purple-50 border-purple-300 text-purple-700 font-bold'
    case 'B': return 'bg-blue-50 border-blue-300 text-blue-700 font-bold'
    case 'C': return 'bg-green-50 border-green-300 text-green-700 font-bold'
    default:  return 'bg-gray-50 border-gray-200 text-gray-500'
  }
}

/** Single-character seal for a skill type (主動→主, 被動→被, …). */
const SKILL_TYPE_MARKS: Record<string, string> = {
  '主動': '主',
  '能動': '主',
  '被動': '被',
  '受動': '被',
  '兵種': '兵',
  '陣法': '陣',
  '指揮': '指',
  '突擊': '突',
  '突撃': '突',
}

export function skillTypeMark(type?: string | null): string {
  if (!type) return ''
  return SKILL_TYPE_MARKS[type] ?? type.charAt(0)
}

/** Visual family for the type seal — gold action, muted passive, brown meta. */
export type SkillTypeTone = 'action' | 'passive' | 'meta' | 'unknown'

export function skillTypeTone(type?: string | null): SkillTypeTone {
  switch (type) {
    case '主動':
    case '能動':
    case '突擊':
    case '突撃':
    case '指揮':
      return 'action'
    case '被動':
    case '受動':
      return 'passive'
    case '兵種':
    case '陣法':
      return 'meta'
    default:
      return 'unknown'
  }
}

// Compact bingxue payload — `d` = CHT direction, `m` = major JP name,
// `n` = array of { n: minor JP name, l: level 1|2 }.
export interface ShareableBingxue {
  d: string | null
  m: string | null
  n: { n: string; l: number }[]
}

export interface ShareableLineup {
  name?: string
  m?: string; m_s1?: string; m_s2?: string; m_st?: any; m_bt?: number; m_bx?: ShareableBingxue
  v1?: string; v1_s1?: string; v1_s2?: string; v1_st?: any; v1_bt?: number; v1_bx?: ShareableBingxue
  v2?: string; v2_s1?: string; v2_s2?: string; v2_st?: any; v2_bt?: number; v2_bx?: ShareableBingxue
}

// v3 envelope — wraps teams under a named group so multi-group payloads can
// round-trip. v2 (`lineups: ShareableLineup[]`) stays as the legacy read path
// and folds into the active group on restore.
//
// v4 additions are optional so v3 share-link blobs still typecheck and the
// share-load codepath stays unchanged. Autosave blobs from that era set v: 4.
//
// v5 splits 自由 / 庫存 into independent team workspaces. Inventory (owned
// heroes/skills) stays global. Share links typically still use v2/v3 and
// apply to the currently selected mode; autosave / cloud / OAuth recovery
// round-trip `workspaces`.
export type CatalogMode = 'free' | 'inventory'
export const CATALOG_MODES: readonly CatalogMode[] = ['free', 'inventory']

export interface ShareableGroup {
  name: string
  teams: ShareableLineup[]
  // v4 — stable client-side id and per-group last-write timestamp.
  // Used by autosave restore to preserve group identity across reloads and,
  // later, by cloud sync to map local groups to DB rows via client_id.
  id?: string
  updated_at?: string
}

export interface ShareableWorkspace {
  active_group_index?: number
  active_team_index?: number
  groups: ShareableGroup[]
}

export interface ShareableData {
  v?: number  // 1 = CHT names, 2 = JP names, 3 = JP names + groups envelope, 4 = v3 + autosave metadata, 5 = dual workspaces.
  inv_h?: string[]
  inv_s?: string[]
  inventory?: string[] // legacy v1 support
  lineups?: ShareableLineup[]  // v1/v2 — flat (single-group) team list
  groups?: ShareableGroup[]    // v3/v4 — named-group envelope (single workspace)
  // v5 — per-mode team graphs. Autosave/cloud/OAuth always write this.
  workspaces?: Record<CatalogMode, ShareableWorkspace>
  // v4 — autosave metadata. Restored on next session to put the user back
  // where they left off (active group index), and used by the cross-tab
  // reconciler (gen counter) and the future cloud-sync handoff (device_id).
  active_group_index?: number
  gen?: number
  device_id?: string
  saved_at?: string  // ISO timestamp of the localStorage write
}