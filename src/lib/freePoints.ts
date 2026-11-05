// A hero's free stat points, for every surface that shows or spends them.

/** Heroes with free points beyond the rule, by cfg_id, from one breakthrough star up. 豐臣秀吉's 立身出世: 每升級10次，獲得3點可分配屬性點數. */
const EXTRA_FREE_POINTS: Readonly<Record<number, number>> = { 10006: 15 }

/** Base 50 free points, +10 per breakthrough star, plus the hero's own extra from one star up. */
export function freePointsTotal(hero: { cfg_id?: number } | null | undefined, breakthrough: number | undefined): number {
  const stars = breakthrough ?? 0
  const extra = stars >= 1 ? (EXTRA_FREE_POINTS[hero?.cfg_id ?? -1] ?? 0) : 0
  return 50 + stars * 10 + extra
}
