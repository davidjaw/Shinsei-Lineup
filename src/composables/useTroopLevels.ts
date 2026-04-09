/**
 * Reactive team-level troop type aggregation.
 *
 * Aggregates troop affinity across all 3 heroes in a lineup,
 * respecting breakthrough-gated trait activation.
 *
 * Formula: effective = min(sum_levels, 10 + sum_level_cap_bonuses)
 */

import { computed, type Ref, type ComputedRef } from 'vue'
import type { Lineup } from './useLineups'
import { TRAIT_UNLOCK, TROOP_TYPES, type TroopType } from '../constants/traits'

export function useTroopLevels(lineup: Ref<Lineup> | ComputedRef<Lineup>) {
  return computed<Record<TroopType, number>>(() => {
    const sums: Record<TroopType, { lv: number; cap: number }> = {} as any
    for (const tt of TROOP_TYPES) {
      sums[tt] = { lv: 0, cap: 0 }
    }

    for (const role of [lineup.value.main, lineup.value.vice1, lineup.value.vice2]) {
      if (!role.hero?.traits) continue
      role.hero.traits.forEach((t, i) => {
        // Trait slot i only active if breakthrough >= TRAIT_UNLOCK[i]
        if (i >= TRAIT_UNLOCK.length || role.breakthrough < TRAIT_UNLOCK[i]) return
        if (!t.affinity) return
        for (const tt of t.affinity.troop_types) {
          if (tt in sums) {
            sums[tt as TroopType].lv += t.affinity.level
            sums[tt as TroopType].cap += t.affinity.level_cap_bonus
          }
        }
      })
    }

    const result = {} as Record<TroopType, number>
    for (const tt of TROOP_TYPES) {
      result[tt] = Math.min(sums[tt].lv, 10 + sums[tt].cap)
    }
    return result
  })
}
