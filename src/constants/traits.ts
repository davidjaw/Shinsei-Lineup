/**
 * Shared trait constants used by both LineupSlot (breakthrough gating)
 * and useTroopLevels (team-level aggregation).
 */

/** Breakthrough stars required to unlock each trait slot (index 0-3). */
export const TRAIT_UNLOCK = [0, 1, 3, 5] as const

/** The five troop types in fixed display order. */
export const TROOP_TYPES = ['足輕', '弓兵', '騎兵', '鐵炮', '器械'] as const
export type TroopType = (typeof TROOP_TYPES)[number]

/** Short display labels for troop chips (2 chars max). */
export const TROOP_LABELS: Record<TroopType, string> = {
  '足輕': '步',
  '弓兵': '弓',
  '騎兵': '騎',
  '鐵炮': '砲',
  '器械': '器',
}
