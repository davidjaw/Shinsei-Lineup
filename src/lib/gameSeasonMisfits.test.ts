// What a picked season leaves out of a group's teams, how the slots are marked, and what clearing removes: a hero
// with its whole slot, a learned skill alone, nothing that changed since the list was made.
import { describe, expect, it } from 'vitest'
import heroesData from '../../.build/heroes.json'
import skillsData from '../../.build/skills.json'
import type { Hero, Skill } from '../composables/useData'
import type { Lineup, RoleData } from '../composables/useLineups'
import {
  clearGameSeasonMisfits, gameSeasonMisfitNames, gameSeasonMisfits, gameSeasonOffer, gameSeasonSlotMarks, offeredHeroes, offeredSkills,
} from './gameSeasonMisfits'

const heroes = heroesData as unknown as Hero[]
const skills = skillsData as unknown as Skill[]
const hero = (name: string): Hero => heroes.find((h) => h.name === name)!
const skill = (name: string): Skill => skills.find((s) => s.name === name)!

const role = (h: string | null, s1: string | null = null, s2: string | null = null): RoleData => ({
  hero: h ? hero(h) : null,
  skill1: s1 ? skill(s1) : null,
  skill2: s2 ? skill(s2) : null,
  stats: { lea: 120, val: 110, int: 100, pol: 90, cha: 80, spd: 70 },
  breakthrough: 3,
  bingxue: { direction: '武略', major: 'x', minors: [{ name: 'y', level: 1 }] },
})

// 伊達政宗 PK, 織田信長 S1, 阿江 universal; 疑兵盜城 S2 (event), 紅蓮之炎 S1 (信長's), 龍騎兵 PK (政宗's),
// 合盟之陣 S3 (event), 追亡逐北 PK (event).
const mixedTeam = (): Lineup => ({
  name: '混合',
  main: role('伊達政宗', '疑兵盜城', '紅蓮之炎'),
  vice1: role('織田信長', '龍騎兵', '合盟之陣'),
  vice2: role('阿江', '追亡逐北'),
})
const plainTeam = (): Lineup => ({ name: '純 S1', main: role('織田信長', '紅蓮之炎'), vice1: role(null), vice2: role(null) })

const misfitsIn = (season: string, teams: Lineup[] = [mixedTeam()]) => gameSeasonMisfits(teams, gameSeasonOffer(season, heroes))

describe('the misfits of a season', () => {
  it('list each hero and learned skill the season does not offer, a hero before its skills', () => {
    expect(misfitsIn('S1')).toEqual([
      { team: 0, role: 'main', slot: null, name: '伊達政宗' },
      { team: 0, role: 'main', slot: 1, name: '疑兵盜城' },
      { team: 0, role: 'vice1', slot: 1, name: '龍騎兵' },
      { team: 0, role: 'vice1', slot: 2, name: '合盟之陣' },
      { team: 0, role: 'vice2', slot: 1, name: '追亡逐北' },
    ])
  })

  it('shrink as the season gets newer, and are none in PK', () => {
    expect(gameSeasonMisfitNames(misfitsIn('S2'))).toEqual(['伊達政宗', '龍騎兵', '合盟之陣', '追亡逐北'])
    expect(gameSeasonMisfitNames(misfitsIn('S3'))).toEqual(['伊達政宗', '龍騎兵', '追亡逐北'])
    expect(misfitsIn('PK')).toEqual([])
  })

  it('never list a universal hero, and say which team each one is on', () => {
    const list = misfitsIn('S1', [plainTeam(), mixedTeam()])
    expect(list.every((m) => m.team === 1)).toBe(true)
    expect(list.map((m) => m.name)).not.toContain('阿江')
  })
})

describe('the marks', () => {
  it('say per slot whether its hero is off-season and which skills are, for the team asked', () => {
    const list = misfitsIn('S1', [plainTeam(), mixedTeam()])
    expect(gameSeasonSlotMarks(list, 0)).toEqual({})
    expect(gameSeasonSlotMarks(list, 1)).toEqual({
      main: { hero: true, skills: [1] },
      vice1: { hero: false, skills: [1, 2] },
      vice2: { hero: false, skills: [1] },
    })
  })
})

describe('clearing', () => {
  it('clears a hero like its slot\'s ✕ (skills, 突破, 兵學), and a skill alone, leaving what fits', () => {
    const teams = [mixedTeam()]
    clearGameSeasonMisfits(teams, misfitsIn('S1', teams))
    const [team] = teams
    expect(team.main).toMatchObject({ hero: null, skill1: null, skill2: null, breakthrough: 0, bingxue: { direction: null, major: null, minors: [] } })
    expect(team.vice1.hero?.name).toBe('織田信長')
    expect([team.vice1.skill1, team.vice1.skill2]).toEqual([null, null])
    expect(team.vice1.breakthrough).toBe(3)
    expect(team.vice2.hero?.name).toBe('阿江')
    expect(team.vice2.skill1).toBeNull()
    expect(misfitsIn('S1', teams)).toEqual([])
  })

  it('leaves a slot alone that holds something else by now', () => {
    const teams = [mixedTeam()]
    const list = misfitsIn('S1', teams)
    teams[0].vice1.skill1 = skill('紅蓮之炎')
    clearGameSeasonMisfits(teams, list)
    expect(teams[0].vice1.skill1?.name).toBe('紅蓮之炎')
  })
})

describe('the pickers\' lists', () => {
  it('are the season\'s heroes and skills; without a season, the whole catalog, which is never narrowed', () => {
    const s1 = gameSeasonOffer('S1', heroes)
    expect(offeredHeroes(heroes, s1).map((h) => h.name)).not.toContain('伊達政宗')
    expect(offeredHeroes(heroes, s1).map((h) => h.name)).toContain('阿江')
    expect(offeredSkills(skills, s1).map((s) => s.name)).not.toContain('疑兵盜城')
    expect(offeredHeroes(heroes, null)).toHaveLength(heroes.length)
    expect(offeredSkills(skills, null)).toHaveLength(skills.length)
    expect(heroes).toHaveLength((heroesData as unknown[]).length)
  })
})
