// The game season as a device preference over the real persistence: it is stored on its own key and in nothing
// else, a non-PK season loses nothing across reloads (the saved blob stays as it was, the team stays whole and is
// marked), clearing and switching act on the active group only, the inventory is never touched, and both
// workspaces follow the same rules.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import heroesData from '../../.build/heroes.json'
import type { ShareableData } from '../constants/gameData'

vi.mock('../lib/bans', () => ({ fetchMyBan: async () => false }))

const STORAGE_KEY = 'nobunaga.groups.v5'
const GAME_SEASON_KEY = 'nobunaga.gameSeason'
const VOLATILE = new Set(['gen', 'saved_at', 'device_id', 'updated_at'])

// 伊達政宗 PK with 疑兵盜城 S2 and 紅蓮之炎 S1; 織田信長 S1 with 龍騎兵 PK and 合盟之陣 S3; 阿江 (every season) with
// 追亡逐北 PK. Keys are name_jp, as saves use them; stats are each hero's base, as picking a hero sets them (restore
// re-anchors saved stats on the base, so a made-up 100 against a x.5 base would move on the first reload).
const baseStats = (jp: string) => (heroesData as { name_jp?: string; stats?: object }[]).find((h) => h.name_jp === jp)!.stats
const MIXED_TEAM = {
  name: '混合隊', m: '伊達政宗', m_s1: '城盗り', m_s2: '紅蓮の炎', m_bt: 3, m_st: baseStats('伊達政宗'),
  v1: '織田信長', v1_s1: '竜騎兵', v1_s2: '会盟の陣', v1_st: baseStats('織田信長'), v2: 'お江', v2_s1: '追い崩し', v2_st: baseStats('お江'),
}
const PLAIN_TEAM = { name: '第二隊', m: '織田信長', m_s1: '紅蓮の炎', m_st: baseStats('織田信長') }

const seed = (season: string | null): void => {
  const blob: ShareableData = {
    v: 5,
    inv_h: ['伊達政宗', '織田信長'],
    inv_s: ['城盗り', '竜騎兵'],
    workspaces: {
      free: { active_group_index: 0, groups: [
        { id: 'f_g_1', name: '自由編組', teams: [MIXED_TEAM, PLAIN_TEAM] },
        { id: 'f_g_2', name: '別的編組', teams: [PLAIN_TEAM] },
      ] },
      inventory: { active_group_index: 0, groups: [{ id: 'i_g_1', name: '庫存編組', teams: [MIXED_TEAM] }] },
    },
  } as ShareableData
  localStorage.setItem(STORAGE_KEY, JSON.stringify(blob))
  if (season) localStorage.setItem(GAME_SEASON_KEY, season)
}

/** A page load: fresh modules, the saved data restored, autosave on, as LineupBuilder's onMounted does. */
const load = async () => {
  vi.resetModules()
  const persistence = (await import('./useGroupPersistence')).useGroupPersistence()
  persistence.restoreFromLocalStorage()
  persistence.enableAutosave()
  const season = (await import('./useGameSeason')).useGameSeason()
  const { useLineups } = await import('./useLineups')
  const { useInventory } = await import('./useInventory')
  const { useGroups } = await import('./useGroups')
  return { ...persistence, ...season, lineups: useLineups().lineups, inventory: useInventory(), groups: useGroups() }
}

const stored = (): string => localStorage.getItem(STORAGE_KEY)!
const content = (raw: string): string => JSON.stringify(JSON.parse(raw), (k, v) => (VOLATILE.has(k) ? undefined : v))
const teamNames = (team: { main: { hero: { name: string } | null }; vice1: { hero: { name: string } | null }; vice2: { hero: { name: string } | null } }) =>
  [team.main.hero?.name ?? null, team.vice1.hero?.name ?? null, team.vice2.hero?.name ?? null]

const openChannels: BroadcastChannel[] = []
const RealChannel = BroadcastChannel

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  vi.stubGlobal('BroadcastChannel', class extends RealChannel {
    constructor(name: string) {
      super(name)
      openChannels.push(this)
    }
  })
  localStorage.clear()
})

afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  openChannels.splice(0).forEach((channel) => channel.close())
})

describe('the preference', () => {
  it('defaults to PK, the newest season, and marks nothing then', async () => {
    seed(null)
    const app = await load()
    expect(app.gameSeason.value).toBe('PK')
    expect(app.gameSeasons).toEqual(['S1', 'S2', 'S3', 'PK'])
    expect(app.misfits.value).toEqual([])
  })

  it('is kept on its own key, and an unknown stored value falls back to PK', async () => {
    seed('S9')
    const app = await load()
    expect(app.gameSeason.value).toBe('PK')
    app.switchGameSeason('S2', false)
    await Promise.resolve()
    expect(localStorage.getItem(GAME_SEASON_KEY)).toBe('S2')
    expect((await load()).gameSeason.value).toBe('S2')
  })

  it('is written into no save: the blob holds no season at all after a switch and a save', async () => {
    seed('S1')
    const app = await load()
    app.switchGameSeason('S3', false)
    app.flushLocalAutosave()
    expect(stored()).not.toMatch(/season/i)
  })
})

describe('a save round-trip under S1 with a PK team in the group', () => {
  it('loses nothing: the stored blob is unchanged over two reloads, the team intact and marked', async () => {
    seed('S1')
    const first = await load()
    first.flushLocalAutosave()
    const saved = stored()
    expect(teamNames(first.lineups[0])).toEqual(['伊達政宗', '織田信長', '阿江'])

    for (let reload = 0; reload < 2; reload++) {
      const app = await load()
      vi.runOnlyPendingTimers()
      expect(stored()).toBe(saved)
      expect(app.gameSeason.value).toBe('S1')
      const [team] = app.lineups
      expect(teamNames(team)).toEqual(['伊達政宗', '織田信長', '阿江'])
      expect([team.main.skill1?.name, team.main.skill2?.name, team.vice1.skill1?.name, team.vice1.skill2?.name, team.vice2.skill1?.name])
        .toEqual(['疑兵盜城', '紅蓮之炎', '龍騎兵', '合盟之陣', '追亡逐北'])
      expect(team.main.breakthrough).toBe(3)
      expect(app.misfits.value.map((m) => m.name)).toEqual(['伊達政宗', '疑兵盜城', '龍騎兵', '合盟之陣', '追亡逐北'])
    }
    // A forced save under S1 writes the same content too: the season drops nothing on the way out.
    ;(await load()).flushLocalAutosave()
    expect(content(stored())).toBe(content(saved))
  })
})

describe('clearing', () => {
  it('removes the misfits from the active group only, saves at once, and leaves the inventory as it was', async () => {
    seed('S1')
    const app = await load()
    const owned = [[...app.inventory.ownedHeroes.value], [...app.inventory.ownedSkills.value]]
    app.clearMisfits()
    expect(teamNames(app.lineups[0])).toEqual([null, '織田信長', '阿江'])
    expect(app.lineups[0].vice1.skill1).toBeNull()
    expect(app.misfits.value).toEqual([])
    const blob = JSON.parse(stored()) as ShareableData
    expect(blob.workspaces!.free!.groups![0].teams[0]).not.toHaveProperty('m')
    expect(blob.workspaces!.inventory!.groups![0].teams[0]).toMatchObject({ m: '伊達政宗' })
    expect([app.inventory.ownedHeroes.value, app.inventory.ownedSkills.value]).toEqual(owned)
    expect(blob.inv_h).toEqual(['伊達政宗', '織田信長'])
  })
})

describe('switching season', () => {
  it('to one that leaves things out: remove and switch clears exactly those', async () => {
    seed('PK')
    const app = await load()
    expect(app.misfitsUnder('S3').map((m) => m.name)).toEqual(['伊達政宗', '龍騎兵', '追亡逐北'])
    app.switchGameSeason('S3', true)
    expect(app.gameSeason.value).toBe('S3')
    expect(teamNames(app.lineups[0])).toEqual([null, '織田信長', '阿江'])
    expect(app.lineups[0].vice1.skill2?.name).toBe('合盟之陣')
    expect(app.misfits.value).toEqual([])
  })

  it('keep and switch leaves everything in place, marked', async () => {
    seed('PK')
    const app = await load()
    const before = stored()
    app.switchGameSeason('S2', false)
    expect(teamNames(app.lineups[0])).toEqual(['伊達政宗', '織田信長', '阿江'])
    expect(app.misfits.value.map((m) => m.name)).toEqual(['伊達政宗', '龍騎兵', '合盟之陣', '追亡逐北'])
    vi.runOnlyPendingTimers()
    expect(stored()).toBe(before)
  })

  it('cancel is not switching: nothing changes', async () => {
    seed('PK')
    const app = await load()
    expect(app.misfitsUnder('S1')).toHaveLength(5)
    expect(app.gameSeason.value).toBe('PK')
    expect(app.misfits.value).toEqual([])
  })

  it('switching group asks nothing: the new group\'s own misfits are marked', async () => {
    seed('S1')
    const app = await load()
    expect(app.misfits.value).toHaveLength(5)
    app.groups.setCurrentGroup(1)
    expect(app.misfits.value).toEqual([])
    app.groups.setCurrentGroup(0)
    expect(app.misfits.value).toHaveLength(5)
  })
})

describe('the inventory workspace', () => {
  it('follows the same rules: its group is marked and cleared alike, and the owned lists stay as they are', async () => {
    seed('S1')
    const app = await load()
    app.inventory.showOwnedOnly.value = true
    expect(app.groups.currentGroup.value.name).toBe('庫存編組')
    expect(app.misfits.value.map((m) => m.name)).toEqual(['伊達政宗', '疑兵盜城', '龍騎兵', '合盟之陣', '追亡逐北'])
    app.clearMisfits()
    expect(teamNames(app.lineups[0])).toEqual([null, '織田信長', '阿江'])
    expect(app.inventory.ownedHeroes.value).toEqual(['伊達政宗', '織田信長'])
    expect(app.inventory.ownedSkills.value).toEqual(['疑兵盜城', '龍騎兵'])
  })
})
