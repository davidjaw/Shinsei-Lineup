import { afterEach, describe, expect, it, vi } from 'vitest'
import { fillStoredTeam, readStoredTeam } from './storedTeam'
import { useData } from '../composables/useData'
import type { Hero, Skill } from '../composables/useData'

const hero = (over: Partial<Hero>): Hero => ({ name: '織田信長', name_jp: '織田信長', faction: '織田', cost: 7, rarity: 5, portrait: 'https://art/nobunaga.png', ...over }) as Hero
const skill = (over: Partial<Skill>): Skill => ({ id: 's1', name: '天下布武', name_jp: '天下布武', icon: 'https://art/s.png', description: '說明', ...over }) as Skill
const catalog = { heroes: [hero({ aliases: ['舊名信長'] })], skills: [skill({})] }

const role = (h: unknown, s: unknown = null) => ({ hero: h, skill1: s, skill2: null, stats: { lea: 150 }, breakthrough: 3, bingxue: { direction: '武略', major: 'x', minors: [{ name: 'y', level: 2 }] } })
const team = (main: unknown, s?: unknown) => ({ name: '新站隊伍', main: role(main, s), vice1: role(null), vice2: role(null) })

describe('fillStoredTeam', () => {
  it('fills the art and the rest a new-site blob lacks', () => {
    const filled = fillStoredTeam(team({ name: '織田信長', cost: 7 }, { name: '天下布武' }), catalog)
    expect(filled.main.hero?.portrait).toBe('https://art/nobunaga.png')
    expect(filled.main.hero?.faction).toBe('織田')
    expect(filled.main.skill1?.description).toBe('說明')
  })

  it('treats an empty or null stored field as missing', () => {
    expect(fillStoredTeam(team({ name: '織田信長', portrait: '' }), catalog).main.hero?.portrait).toBe('https://art/nobunaga.png')
    expect(fillStoredTeam(team({ name: '織田信長', portrait: null }), catalog).main.hero?.portrait).toBe('https://art/nobunaga.png')
  })

  it('keeps what the row holds, so the server hash of a handed-back team stays the same', () => {
    const filled = fillStoredTeam(team({ name: '舊名信長', portrait: 'https://art/old.png' }), catalog)
    expect(filled.main.hero?.name).toBe('舊名信長') // resolved by alias, name untouched
    expect(filled.main.hero?.portrait).toBe('https://art/old.png')
    expect(filled.main.stats).toEqual({ lea: 150 })
    expect(filled.main.breakthrough).toBe(3)
    expect(filled.main.bingxue.minors).toEqual([{ name: 'y', level: 2 }])
    expect(filled.name).toBe('新站隊伍')
  })

  it('leaves a name the catalog does not know, empty slots and odd blobs alone', () => {
    const unknown = { name: '未知武將' }
    const filled = fillStoredTeam(team(unknown), catalog)
    expect(filled.main.hero).toEqual(unknown)
    expect(filled.vice1.hero).toBeNull()
    expect(fillStoredTeam(null, catalog)).toBeNull()
    expect(fillStoredTeam({ name: 'x' }, catalog).main).toBeUndefined()
  })

  it('does not change the stored blob', () => {
    const stored = team({ name: '織田信長' })
    fillStoredTeam(stored, catalog)
    expect(stored.main.hero).toEqual({ name: '織田信長' })
  })
})

describe('readStoredTeam', () => {
  it('reads the real catalog and yields something a snapshot can clone', () => {
    const live = useData().heroes.value.find((h) => h.portrait)!
    const filled = readStoredTeam(team({ name: live.name }))
    expect(filled.main.hero?.portrait).toBe(live.portrait)
    expect(() => structuredClone(filled)).not.toThrow()
  })
})

describe('every read of a stored team', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  const stubbed = async (rows: unknown[]) => {
    vi.resetModules()
    vi.stubEnv('VITE_SUPABASE_URL', 'https://stub.test')
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'stub-key')
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(rows))))
    const live = (await import('../composables/useData')).useData().heroes.value.find((h) => h.portrait)!
    return { live, blob: team({ name: live.name }) }
  }

  it('fills the feed sample, the variant list and my proposals', async () => {
    const { live, blob } = await stubbed([])
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([{ sample_team_blob: blob, team_blob: blob }]))))
    const variants = await import('./variants')
    expect((await variants.listHeroSets())[0].sampleTeam.main.hero?.portrait).toBe(live.portrait)
    expect((await variants.listVariantsInSet('h'))[0].team.main.hero?.portrait).toBe(live.portrait)

    localStorage.setItem('nobunaga.auth.session', JSON.stringify({
      access_token: `h.${btoa(JSON.stringify({ sub: 'u' }))}.s`,
      refresh_token: 'r',
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      user: { id: 'u', email: 'u@mail.test', display_name: null },
    }))
    const proposals = await import('./proposals')
    expect((await proposals.listMyProposals())[0].team.main.hero?.portrait).toBe(live.portrait)
  })
})

describe('the module graph', () => {
  // useGroups runs an immediate watch on useInventory at load, so anything useInventory
  // reaches must not lead back to useGroups: that hits useInventory before it initializes.
  it('loads useInventory first without a circular-import failure', async () => {
    vi.resetModules()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    await import('../composables/useInventory')
    const warnings = warn.mock.calls.map((c) => String(c[0]))
    warn.mockRestore()
    expect(warnings.filter((w) => w.includes('Unhandled error'))).toEqual([])
  })
})
