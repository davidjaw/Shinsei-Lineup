// The game-season table (data/game_seasons.json) against the catalog it describes (.build/*.json): a hero or
// equippable event skill added to the catalog without a season, a key the catalog does not know, a value outside the
// season order, an equippable skill whose season cannot be found, or an entry still undecided fails here; and the
// official cfg_id, which runs in release order, never goes back a season. And what a picked season offers.
import { describe, expect, it } from 'vitest'
import heroesData from '../../.build/heroes.json'
import skillsData from '../../.build/skills.json'
import { isEquippableSkillType } from '../constants/gameData'
import type { Hero, Skill } from '../composables/useData'
import { GAME_SEASON_UNIVERSAL_HEROES, GAME_SEASONS, gameSeasonOffered, gameSeasonsOf, latestGameSeason, type GameSeasonTable } from './gameSeason'

const heroes = heroesData as unknown as Hero[]
const skills = skillsData as unknown as Skill[]
const keyOf = (row: { name: string; name_jp?: string | null }) => row.name_jp || row.name
const seasons = gameSeasonsOf(heroes)
const equippable = skills.filter((s) => isEquippableSkillType(s.type))
const skill = (name: string) => skills.find((s) => s.name === name)!
const hero = (name: string) => heroes.find((h) => h.name === name)!

describe('the game-season table', () => {
  it('has the four ruled seasons, oldest first, and an undecided value outside them', () => {
    expect(GAME_SEASONS.order).toEqual(['S1', 'S2', 'S3', 'PK'])
    expect(GAME_SEASONS.order).not.toContain(GAME_SEASONS.undecided)
    expect(latestGameSeason()).toBe('PK')
  })

  it('names every hero of the catalog, and no key the catalog does not know', () => {
    const keys = heroes.map(keyOf)
    expect(keys.filter((key) => !(key in GAME_SEASONS.heroes))).toEqual([])
    expect(Object.keys(GAME_SEASONS.heroes).filter((key) => !keys.includes(key))).toEqual([])
  })

  it('names every equippable event skill, and lists only skills with no hero of their own', () => {
    const keys = equippable.map(keyOf)
    expect(equippable.filter((s) => s.is_event_skill && !(keyOf(s) in GAME_SEASONS.skills)).map((s) => s.name)).toEqual([])
    expect(Object.keys(GAME_SEASONS.skills).filter((key) => !keys.includes(key))).toEqual([])
    expect(skills.filter((s) => keyOf(s) in GAME_SEASONS.skills && seasons.heroOf(s)).map((s) => s.name)).toEqual([])
  })

  it('has every value in the season order, none undecided', () => {
    const values = [...Object.values(GAME_SEASONS.heroes), ...Object.values(GAME_SEASONS.skills)]
    expect(values.filter((v) => !GAME_SEASONS.order.includes(v))).toEqual([])
  })

  it('finds a season for every hero and every equippable skill of the catalog', () => {
    expect(heroes.filter((h) => seasons.hero(h) === null).map((h) => h.name)).toEqual([])
    expect(equippable.filter((s) => seasons.skill(s) === null).map((s) => s.name)).toEqual([])
  })

  it('agrees with the cfg_id, which runs in release order: within a run of ids, a hero\'s skill never goes back a season', () => {
    // A run is a thousand ids (20xxx the heroes' own skills, 24xxx and 29xxx two later-numbered sets). The universal
    // heroes are S1 by ruling, not by release, so their skills are left out. OPEN: four skills sit early in 20xxx but
    // their heroes are of a later season; reported to the owner, the data is not bent to fit. The test fails when one
    // more appears, or when one of these is settled, so the list stays true.
    const OPEN = ['20010 表裡比興 S3', '20024 天下御免 S2', '20035 越後二天 S3', '20091 縱橫馳突 S2']
    const universal = new Set(GAME_SEASON_UNIVERSAL_HEROES)
    const rank = (s: Skill) => GAME_SEASONS.order.indexOf(seasons.skill(s)!)
    const label = (s: Skill) => `${s.cfg_id} ${s.name} ${seasons.skill(s)}`
    const run = (s: Skill) => Math.floor(s.cfg_id! / 1000)
    const derived = equippable
      .filter((s) => s.cfg_id != null && !(keyOf(s) in GAME_SEASONS.skills) && seasons.heroOf(s) && !universal.has(keyOf(seasons.heroOf(s)!)))
      .sort((a, b) => a.cfg_id! - b.cfg_id!)
    const early = derived.filter((s, i) => derived.slice(i + 1).some((e) => run(e) === run(s) && rank(e) < rank(s)))
    expect(early.map(label)).toEqual(OPEN)
    const rest = derived.filter((s) => !early.includes(s))
    expect(rest.filter((s, i) => i > 0 && run(rest[i - 1]) === run(s) && rank(rest[i - 1]) > rank(s)).map(label)).toEqual([])
  })
})

describe('universal heroes', () => {
  it('are listed S1, which every season offers', () => {
    for (const key of GAME_SEASON_UNIVERSAL_HEROES) {
      expect(GAME_SEASONS.heroes[key]).toBe('S1')
      for (const selected of GAME_SEASONS.order) expect(gameSeasonOffered(GAME_SEASONS.heroes[key], selected)).toBe(true)
    }
  })

  it('are the five the owner named, under their display names', () => {
    const names = heroes.filter((h) => GAME_SEASON_UNIVERSAL_HEROES.includes(keyOf(h))).map((h) => h.name).sort()
    expect(names).toEqual(['上泉信綱', '柳生宗嚴', '真田大助', '阿初', '阿江'].sort())
  })
})

describe('a skill\'s season', () => {
  it('is its hero\'s, by source_hero or unique_hero under either of the hero\'s names', () => {
    // source_hero 長宗我部国親 (name_jp), and unique_hero 長宗我部國親 (name) on a skill with no source_hero.
    expect(seasons.skill(skill('當機立斷'))).toBe('PK')
    expect(seasons.skill(skill('野之虎'))).toBe('PK')
    expect(seasons.skill(skill('武田之赤備'))).toBe(GAME_SEASONS.heroes['山県昌景'])
  })

  it('of a teachable skill follows the hero who teaches it', () => {
    const teachable = skills.filter((s) => s.is_teachable && seasons.heroOf(s))
    expect(teachable.length).toBeGreaterThan(100)
    for (const s of teachable) expect(seasons.skill(s)).toBe(seasons.hero(seasons.heroOf(s)!))
    expect(seasons.skill(skill(hero('伊達政宗').teachable_skill!))).toBe('PK')
  })

  it('of an event skill comes from the table: S2 22001-22010, S3 22011-22014, PK the rest', () => {
    const events = equippable.filter((s) => s.is_event_skill)
    const bySeason = (season: string) => events.filter((s) => seasons.skill(s) === season).map((s) => s.name).sort()
    expect(bySeason('S1')).toEqual([])
    expect(bySeason('S2')).toEqual(['疑兵盜城', '專橫專斷', '立身之志', '離心背道', '同盟姻親', '斬雷神', '乘虛而入', '破天轟鳴', '家中整飭', '大器之蘊'].sort())
    expect(bySeason('S3')).toEqual(['合盟之陣', '直言極諫', '疑心暗鬼', '南蠻東渡'].sort())
    expect(bySeason('PK')).toEqual(['追亡逐北', '出奇制勝', '越後先手組', '三河武士', '甲斐弓騎兵·拓', '以逸待勞', '誘敵深入', '孤注一擲', '能鷹隱爪'].sort())
    for (const s of events.filter((e) => seasons.skill(e) !== 'PK')) {
      expect(s.cfg_id).toBeGreaterThanOrEqual(seasons.skill(s) === 'S2' ? 22001 : 22011)
      expect(s.cfg_id).toBeLessThanOrEqual(seasons.skill(s) === 'S2' ? 22010 : 22014)
    }
  })
})

describe('what a season offers', () => {
  const data: GameSeasonTable = { order: ['S1', 'S2', 'S3', 'PK'], undecided: '未定', heroes: {}, skills: {} }

  it('adds up: a season offers what it and every earlier season brought', () => {
    const offered = (season: string) => data.order.filter((selected) => gameSeasonOffered(season, selected, data))
    expect(offered('S1')).toEqual(['S1', 'S2', 'S3', 'PK'])
    expect(offered('S2')).toEqual(['S2', 'S3', 'PK'])
    expect(offered('S3')).toEqual(['S3', 'PK'])
    expect(offered('PK')).toEqual(['PK'])
  })

  it('offers an undecided entry, or one the table does not know, in every season', () => {
    for (const selected of data.order) {
      expect(gameSeasonOffered('未定', selected, data)).toBe(true)
      expect(gameSeasonOffered(null, selected, data)).toBe(true)
    }
  })

  it('in the real catalog: S1 offers the 133 S1 heroes, PK every hero', () => {
    const count = (selected: string) => heroes.filter((h) => gameSeasonOffered(seasons.hero(h), selected)).length
    expect([count('S1'), count('S2'), count('S3'), count('PK')]).toEqual([133, 141, 149, 167])
  })
})
