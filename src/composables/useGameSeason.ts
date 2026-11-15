// The game season the lineup page offers (S1, S2, S3, PK; ../lib/gameSeason.ts): this device's preference, kept the
// way nobunaga.catalogMode is (./useInventory.ts) and never in a save, a share, a cloud row or any table (the paid
// site reads the same cloud data). It only narrows what the pickers offer and marks what does not fit; the catalog
// (useData) stays whole. Default: the newest season, so nothing changes for someone who never picks one.
//
// What it does not offer on the active group is marked where it stands. Clearing removes it; switching to a season
// that would leave something out lets the page ask first (clear and switch, keep and switch, or cancel). Switching
// the group asks nothing: its own misfits are simply marked.
import { computed, ref, watch } from 'vue'
import { GAME_SEASONS, latestGameSeason } from '../lib/gameSeason'
import { clearGameSeasonMisfits, gameSeasonMisfits, gameSeasonOffer, type GameSeasonMisfit } from '../lib/gameSeasonMisfits'
import { useData } from './useData'
import { useGroupPersistence } from './useGroupPersistence'
import { useLineups } from './useLineups'

const GAME_SEASON_KEY = 'nobunaga.gameSeason'

function readStoredGameSeason(): string {
  try {
    const stored = localStorage.getItem(GAME_SEASON_KEY)
    return stored && GAME_SEASONS.order.includes(stored) ? stored : latestGameSeason()
  } catch {
    return latestGameSeason()
  }
}

const gameSeason = ref(readStoredGameSeason())

watch(gameSeason, (value) => {
  try {
    localStorage.setItem(GAME_SEASON_KEY, value)
  } catch {
    // localStorage may be unavailable (private mode / quota): the pick then lasts this page.
  }
})

const { heroes } = useData()
const { lineups } = useLineups()

const offer = computed(() => gameSeasonOffer(gameSeason.value, heroes.value))
const misfits = computed(() => gameSeasonMisfits(lineups, offer.value))

/** What `season` would leave out of the active group. */
const misfitsUnder = (season: string): GameSeasonMisfit[] =>
  gameSeasonMisfits(lineups, gameSeasonOffer(season, heroes.value))

/** Clears `list` (default: the current misfits) from the active group and saves at once. */
function clearMisfits(list: readonly GameSeasonMisfit[] = misfits.value): void {
  clearGameSeasonMisfits(lineups, list)
  useGroupPersistence().flushLocalAutosave()
}

/** Switches to `season`; `clearing` first clears what it would not offer. */
function switchGameSeason(season: string, clearing: boolean): void {
  if (clearing) clearMisfits(misfitsUnder(season))
  gameSeason.value = season
}

export function useGameSeason() {
  return {
    gameSeason,
    gameSeasons: GAME_SEASONS.order,
    offer,
    misfits,
    misfitsUnder,
    clearMisfits,
    switchGameSeason,
  }
}
