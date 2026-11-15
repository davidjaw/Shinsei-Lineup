// The game season (S1, S2, S3, PK) each hero and skill first came with, read from the hand-maintained table
// data/game_seasons.json (neither the crawl nor the official cfg has such a field). Seasons add up: a season offers
// what it and every earlier one brought. Everything after S3 is PK (no PK1 / PK2 / PK3), as the owner ruled on
// 2026-11-15. The word "season" means other things elsewhere in this product family, so this one is always
// "gameSeason".
//
// The table names every hero by its key (name_jp, as saves and shares use it) and the skills with no hero of their
// own (the event skills); any other skill takes its hero's season (source_hero, else unique_hero, matched under
// either of the hero's names), a teachable one too. 評定眾 and season effects are not in it: they are never equipped.
// An entry nobody has checked yet holds `undecided` and counts as offered in every season, so a guess never hides
// anything. src/lib/gameSeason.test.ts holds the table to the catalog.
//
// Event skills: their season follows the official cfg_id, which runs in release order. 20180 and up are PK; the
// separate run 22001-22010 is S2 and 22011-22014 S3, inferred from the cfg's order and still to be confirmed.
import table from '../../data/game_seasons.json'
import type { Hero, Skill } from '../composables/useData'

export interface GameSeasonTable {
  /** Oldest first; a new season is one more entry here. */
  order: string[]
  /** The value of an entry not yet checked. */
  undecided: string
  /** Every hero, by name_jp. */
  heroes: Record<string, string>
  /** Skills with no hero of their own (event skills), by name_jp. */
  skills: Record<string, string>
}

export const GAME_SEASONS: GameSeasonTable = table

/** Heroes the owner ruled to be in every season (2026-11-15); the table lists them as S1. */
export const GAME_SEASON_UNIVERSAL_HEROES: readonly string[] = ['柳生宗厳', '上泉信綱', 'お江', 'お初', '真田大助']

/** The newest season of the table: the default, so someone who never picks one sees no change. */
export const latestGameSeason = (data: GameSeasonTable = GAME_SEASONS): string => data.order[data.order.length - 1]

export type HeroRow = Pick<Hero, 'name' | 'name_jp'>
export type SkillRow = Pick<Skill, 'name' | 'name_jp' | 'source_hero' | 'unique_hero'>

/** The key saves, shares and the table use. */
const keyOf = (row: { name: string; name_jp?: string | null }): string => row.name_jp || row.name

/** The game season of each hero and skill of a catalog; null for one the table does not know. */
export function gameSeasonsOf(heroes: readonly HeroRow[], data: GameSeasonTable = GAME_SEASONS) {
  const byName = new Map<string, HeroRow>()
  for (const hero of heroes) {
    byName.set(hero.name, hero)
    byName.set(keyOf(hero), hero)
  }
  const hero = (row: HeroRow): string | null => data.heroes[keyOf(row)] ?? null
  /** The hero a skill comes from, by source_hero or unique_hero under either of the hero's names. */
  const heroOf = (skill: SkillRow): HeroRow | null => byName.get(skill.source_hero || skill.unique_hero || '') ?? null
  const skill = (row: SkillRow): string | null => {
    const listed = data.skills[keyOf(row)]
    if (listed !== undefined) return listed
    const from = heroOf(row)
    return from ? hero(from) : null
  }
  return { hero, skill, heroOf }
}

/**
 * Whether something of `season` is offered when `selected` is picked: it came in that season or an earlier one.
 * An undecided entry, or one the table does not know (null), is offered everywhere.
 */
export function gameSeasonOffered(season: string | null, selected: string, data: GameSeasonTable = GAME_SEASONS): boolean {
  const at = season === null ? -1 : data.order.indexOf(season)
  return at < 0 || at <= data.order.indexOf(selected)
}
