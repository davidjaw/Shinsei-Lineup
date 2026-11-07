import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CloudLineupGroup } from '../lib/lineupGroups'
import type { ShareableData, ShareableGroup } from '../constants/gameData'

const cloud = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  bulk: vi.fn(),
  patch: vi.fn(),
  force: vi.fn(),
  remove: vi.fn(),
  share: vi.fn(),
}))

vi.mock('../lib/lineupGroups', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/lineupGroups')>()),
  listMyLineupGroups: cloud.list,
  createLineupGroup: cloud.create,
  bulkCreateLineupGroups: cloud.bulk,
  patchLineupGroupWithLock: cloud.patch,
  patchLineupGroupForce: cloud.force,
  deleteLineupGroup: cloud.remove,
}))
vi.mock('../lib/share', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/share')>()),
  createShare: cloud.share,
}))
vi.mock('../lib/bans', () => ({ fetchMyBan: async () => false }))

const SESSION_KEY = 'nobunaga.auth.session'
const STORAGE_KEY = 'nobunaga.groups.v5'
const metaKey = (user: string): string => `nobunaga.cloud_sync_meta.${user}`

const jwt = (user: string, session?: string): string => {
  const claims = { sub: user, email: `${user}@mail.test`, ...(session ? { session_id: session } : {}) }
  return `h.${btoa(JSON.stringify(claims))}.s`
}

const signIn = (user: string, session?: string): void => {
  localStorage.setItem(SESSION_KEY, JSON.stringify({
    access_token: jwt(user, session),
    refresh_token: 'r',
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: { id: user, email: `${user}@mail.test`, display_name: null },
  }))
}

// Mocks read their last arguments: each call names its account first.
const lastArg = <T>(call: unknown[]): T => call[call.length - 1] as T
const writesOf = (mock: { mock: { calls: unknown[][] } }): string[] =>
  mock.mock.calls.map((c) => lastArg<{ client_id: string }>(c).client_id).sort()

const row = (g: ShareableGroup, i = 0): CloudLineupGroup => ({
  id: `row_${g.id}`,
  user_id: 'x',
  client_id: g.id ?? null,
  name: g.name,
  teams: g.teams,
  sort_order: i,
  updated_at: '2026-11-07T00:00:00Z',
}) as unknown as CloudLineupGroup

const load = async () => {
  vi.resetModules()
  const persistence = (await import('./useGroupPersistence')).useGroupPersistence()
  const { useGroups } = await import('./useGroups')
  const { useData } = await import('./useData')
  const serialize = await import('../lib/lineupSerialize')
  const auth = await import('../lib/auth')
  return { ...persistence, useGroups, useData, serialize, auth }
}

type Loaded = Awaited<ReturnType<typeof load>>

// The local groups of the seeded blob, as this client serializes them.
const localGroups = (app: Loaded): ShareableGroup[] => {
  const { heroes, skills } = app.useData()
  const deps = { heroes: heroes.value, skills: skills.value }
  const { hydrateShareableGroups, makeSerializer } = app.serialize
  const hydrated = hydrateShareableGroups(seedGroups(heroKey(app)), deps, [])
  return hydrated.map((g) => ({ id: g.id, name: g.name, teams: g.teams.map((t) => makeSerializer(deps).serializeLineup(t)) }))
}

const heroKey = (app: Pick<Loaded, 'useData'>): string => app.useData().heroes.value[0].name

const seedGroups = (hero: string): ShareableGroup[] => [
  { id: 'f_g_1', name: '自由編組', teams: [{ name: '第一隊', m: hero }] },
  { id: 'i_g_1', name: '庫存編組', teams: [{ name: '第一隊', m: hero }] },
] as ShareableGroup[]

const seedLocal = async (): Promise<void> => {
  const { useData } = await import('./useData')
  const [free, inventory] = seedGroups(useData().heroes.value[0].name)
  const blob: ShareableData = {
    v: 5,
    workspaces: {
      free: { active_group_index: 0, groups: [free] },
      inventory: { active_group_index: 0, groups: [inventory] },
    },
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(blob))
}

const storedGroupNames = (): string[] => {
  const blob = JSON.parse(localStorage.getItem(STORAGE_KEY)!) as ShareableData
  return (['free', 'inventory'] as const).flatMap((m) => blob.workspaces![m]!.groups!.map((g) => g.name))
}

const expectNoWrites = (): void => {
  for (const write of [cloud.create, cloud.bulk, cloud.patch, cloud.force, cloud.remove]) {
    expect(write).not.toHaveBeenCalled()
  }
}

// An edit, the local save it causes, and the cloud push that save would queue.
// Used as a positive control too: with sync agreed it does write.
const editAndPush = async (app: Loaded): Promise<void> => {
  app.useGroups().workspaces.free.groups[0].name = '改過的編組'
  app.flushLocalAutosave()
  await app.flushPendingCloudPush()
}

// Each load() is a new module instance, and an old one must not reach the next test:
// its debounced save would land in the storage that test starts from.
const RealChannel = BroadcastChannel
const openChannels: BroadcastChannel[] = []

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  openChannels.splice(0).forEach((channel) => channel.close())
})

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  vi.stubGlobal('BroadcastChannel', class extends RealChannel {
    constructor(name: string) {
      super(name)
      openChannels.push(this)
    }
  })
  localStorage.clear()
  vi.clearAllMocks()
  cloud.list.mockReset().mockResolvedValue([])
  cloud.share.mockReset().mockResolvedValue('backupslug00')
  cloud.create.mockReset().mockImplementation(async (...args: unknown[]) => {
    const input = lastArg<ShareableGroup & { client_id: string }>(args)
    return { row: row({ id: input.client_id, name: input.name, teams: input.teams }), adopted: false }
  })
  cloud.bulk.mockReset().mockImplementation(async (...args: unknown[]) =>
    lastArg<(ShareableGroup & { client_id: string })[]>(args).map((input, i) =>
      row({ id: input.client_id, name: input.name, teams: input.teams }, i)))
  cloud.patch.mockReset().mockImplementation(async (...args: unknown[]) => {
    const [id, , patch] = args.slice(-3) as [string, string, ShareableGroup]
    return { kind: 'ok', row: { ...row({ id: id.replace('row_', ''), name: patch.name, teams: patch.teams! }), id } }
  })
  cloud.remove.mockReset().mockResolvedValue(undefined)
})

const cloudRow = (app: Loaded, id = 'f_g_9', name = '雲端編組'): CloudLineupGroup =>
  row({ id, name, teams: [{ name: 't', m: heroKey(app) }] } as ShareableGroup)

/** Local seeded, signed in, the dialog up over the given cloud. */
const atDialog = async (rows: (app: Loaded) => CloudLineupGroup[] = () => [], user = 'userA'): Promise<Loaded> => {
  await seedLocal()
  signIn(user, `sess_${user}`)
  const app = await load()
  cloud.list.mockResolvedValue(rows(app))
  await app.tryBootstrapCloudSync()
  expect(app.cloudMerge.value).not.toBeNull()
  expectNoWrites()
  return app
}

const localNames = (app: Loaded): string[] =>
  (['free', 'inventory'] as const).flatMap((m) => app.useGroups().workspaces[m].groups.map((g) => g.name))

describe('another account on the same browser', () => {
  it("does not upload A's groups into empty account B: the dialog asks, and an edit stays local", async () => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify({ session: 'sessA', rows: { f_g_1: { cloudId: 'row_a', serverUpdatedAt: 't' } } }))
    signIn('userB', 'sessB')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(cloud.list).toHaveBeenCalledTimes(1)
    expect(app.cloudMerge.value?.cloudRows).toEqual([])
    await editAndPush(app)
    expectNoWrites()
  })

  it('stops pushing once a sibling tab signed another account in', async () => {
    await seedLocal()
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue(localGroups(app).map(row))
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).toBeNull()
    signIn('userB', 'sessB') // no event reaches this page
    await editAndPush(app)
    expectNoWrites()
  })

  it('starts over when this page hears of the new session, dropping what A had queued', async () => {
    await seedLocal()
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue(localGroups(app).map(row))
    await app.tryBootstrapCloudSync()
    app.enableAutosave()
    app.useGroups().workspaces.free.groups[0].name = 'A 的編輯'
    app.flushLocalAutosave() // queued, not sent

    cloud.list.mockResolvedValue([])
    app.auth.handleAuthCallback(`#access_token=${jwt('userB', 'sessB')}&refresh_token=r&expires_in=3600`)
    await vi.waitFor(() => expect(app.cloudMerge.value).not.toBeNull())
    await app.flushPendingCloudPush()
    expectNoWrites()
  })

  it('keeps the push across a token refresh of the same session', async () => {
    await seedLocal()
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue(localGroups(app).map(row))
    await app.tryBootstrapCloudSync()
    app.enableAutosave()
    app.auth.handleAuthCallback(`#access_token=${jwt('userA', 'sessA')}&refresh_token=r2&expires_in=3600`)
    expect(cloud.list).toHaveBeenCalledTimes(1)
    await editAndPush(app)
    expect(cloud.patch).toHaveBeenCalled()
  })

  it('does not fall back to an insert when the session moved during a PATCH', async () => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify({ session: 'sessA', rows: {
      f_g_1: { cloudId: 'row_f_g_1', serverUpdatedAt: 't', contentHash: 'old' },
      i_g_1: { cloudId: 'row_i_g_1', serverUpdatedAt: 't', contentHash: 'old' },
    } }))
    signIn('userA', 'sessA')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(cloud.list).not.toHaveBeenCalled()
    cloud.patch.mockImplementation(async () => {
      signIn('userB', 'sessB')
      return { kind: 'deleted' }
    })
    await editAndPush(app)
    expect(cloud.create).not.toHaveBeenCalled()
    expect(cloud.bulk).not.toHaveBeenCalled()
  })

  it.each([
    ['keep-local', 'resolveMergeKeepLocal'],
    ['keep-cloud', 'resolveMergeKeepCloud'],
  ] as const)('sends nothing under B when a sibling signs B in during the %s backup', async (_label, resolve) => {
    const app = await atDialog((a) => [cloudRow(a)])
    cloud.share.mockImplementation(async () => {
      signIn('userB', 'sessB')
      return 'backupslug00'
    })
    const res = await app[resolve]()
    expect(res.kind).toBe('cancel')
    expectNoWrites()
    expect(localNames(app)).toEqual(['自由編組', '庫存編組'])
  })

  it('sends nothing when the session moved before the decision list answered', async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    const rows = [cloudRow(app)]
    cloud.list.mockImplementation(async () => {
      signIn('userB', 'sessB')
      return rows
    })
    expect((await app.resolveMergeAppend()).kind).toBe('cancel')
    expect(app.useGroups().workspaces.free.groups.map((g) => g.name)).toEqual(['自由編組'])
    await app.flushPendingCloudPush()
    expectNoWrites()
  })
})

describe('whether stored meta is trusted', () => {
  const rows = { f_g_1: { cloudId: 'row_f_g_1', serverUpdatedAt: 't' }, i_g_1: { cloudId: 'row_i_g_1', serverUpdatedAt: 't' } }

  it('trusts meta written in this very session: no list, no dialog, pushes go', async () => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify({ session: 'sessA', rows }))
    signIn('userA', 'sessA')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(cloud.list).not.toHaveBeenCalled()
    expect(app.cloudMerge.value).toBeNull()
    await editAndPush(app)
    expect(cloud.patch).toHaveBeenCalled()
  })

  it('does not trust the same account after another sign-in', async () => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify({ session: 'old', rows }))
    signIn('userA', 'new')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(cloud.list).toHaveBeenCalledTimes(1)
    expect(app.cloudMerge.value).not.toBeNull()
    expectNoWrites()
  })

  it.each([
    ['null', { session: null, rows }],
    ['missing', { rows }],
  ])('does not let a token without session_id match a %s stamp', async (_label, stored) => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify(stored))
    signIn('userA')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(cloud.list).toHaveBeenCalledTimes(1)
    expect(app.cloudMerge.value).not.toBeNull()
    expectNoWrites()
  })

  it('takes legacy meta (a flat map) as none, and discards nothing when local differs', async () => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify(rows))
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue([cloudRow(app, 'i_g_9')])
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).not.toBeNull()
    expect(storedGroupNames()).toEqual(['自由編組', '庫存編組'])
    expectNoWrites()
  })

  it('takes legacy meta over equal rows with no dialog and no write, and an edit then writes only its group', async () => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify(rows))
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue(localGroups(app).map(row))
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).toBeNull()
    expectNoWrites()
    const stored = JSON.parse(localStorage.getItem(metaKey('userA'))!)
    expect(stored.session).toBe('sessA')
    expect(Object.keys(stored.rows).sort()).toEqual(['f_g_1', 'i_g_1'])

    await editAndPush(app)
    expect(cloud.patch.mock.calls.map((c) => (c as unknown[]).slice(-3)[0])).toEqual(['row_f_g_1'])
    expect(cloud.create).not.toHaveBeenCalled()
  })
})

describe('a first-time user: signed in, local work, empty cloud', () => {
  it('gets the data up through 兩邊都保留, and the next load trusts the sync', async () => {
    const app = await atDialog()
    expect((await app.resolveMergeAppend()).kind).toBe('append')
    expect(app.cloudMerge.value).toBeNull()
    await app.flushPendingCloudPush()
    expect(writesOf(cloud.create)).toEqual(['f_g_1', 'i_g_1'])
    expect(storedGroupNames()).toEqual(['自由編組', '庫存編組'])
    expect(JSON.parse(localStorage.getItem(metaKey('userA'))!).session).toBe('sess_userA')

    cloud.list.mockClear()
    const reloaded = await load()
    await reloaded.tryBootstrapCloudSync()
    expect(cloud.list).not.toHaveBeenCalled()
    expect(reloaded.cloudMerge.value).toBeNull()
  })

  it('gets the data up through 採用這台裝置, with no pointless backup of nothing', async () => {
    const app = await atDialog()
    const res = await app.resolveMergeKeepLocal()
    expect(res.kind).toBe('keep-local')
    expect(res.backupSlug).toBeUndefined()
    expect(cloud.share).not.toHaveBeenCalled()
    expect(lastArg<unknown[]>(cloud.bulk.mock.calls[0])).toHaveLength(2)
  })

  it('holds everything back on 稍後再決定, and asks again on the next load', async () => {
    const app = await atDialog()
    app.resolveMergeCancel()
    await editAndPush(app)
    expectNoWrites()
    const reloaded = await load()
    await reloaded.tryBootstrapCloudSync()
    expect(reloaded.cloudMerge.value).not.toBeNull()
  })
})

describe('finding 1: keep-cloud over an empty account', () => {
  it('refuses: every local group stays, and no backup lands under this account', async () => {
    const app = await atDialog(() => [], 'userB')
    const res = await app.resolveMergeKeepCloud()
    expect(res.kind).toBe('cancel')
    expect(localNames(app)).toEqual(['自由編組', '庫存編組'])
    expect(storedGroupNames()).toEqual(['自由編組', '庫存編組'])
    expect(cloud.share).not.toHaveBeenCalled()
  })

  it('counts a row of an untouched group as nothing to keep', async () => {
    const app = await atDialog(() => [row({ id: 'f_g_0', name: '預設', teams: [{ name: '隊伍 1' }] } as ShareableGroup)], 'userB')
    expect((await app.resolveMergeKeepCloud()).kind).toBe('cancel')
    expect(localNames(app)).toEqual(['自由編組', '庫存編組'])
  })

  it('still works over a cloud that holds something, backing local up first', async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    const res = await app.resolveMergeKeepCloud()
    expect(res.kind).toBe('keep-cloud')
    const backup = cloud.share.mock.calls[0][0] as ShareableData
    expect(backup.workspaces!.free!.groups![0].name).toBe('自由編組')
    expect(localNames(app)).toContain('雲端編組')
  })

  it('keeps local when its backup fails', async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    cloud.share.mockRejectedValue(new Error('offline'))
    expect(await app.resolveMergeKeepCloud()).toEqual({ kind: 'cancel', backupFailed: true })
    expect(app.cloudMerge.value).not.toBeNull()
    expect(localNames(app)).toEqual(['自由編組', '庫存編組'])
  })
})

describe('the preselected option', () => {
  const OWNER_KEY = 'nobunaga.local_data_account'

  const dialogFor = async (owner: string | null, rows: (app: Loaded) => CloudLineupGroup[]): Promise<Loaded> => {
    if (owner) localStorage.setItem(OWNER_KEY, owner)
    return atDialog(rows)
  }
  const noRows = (): CloudLineupGroup[] => []
  const someRows = (app: Loaded): CloudLineupGroup[] => [cloudRow(app)]

  it.each([
    ['known other', 'userZ', 'other', 'empty', noRows, null],
    ['known other', 'userZ', 'other', 'non-empty', someRows, 'keep-cloud'],
    ['unknown', null, 'unknown', 'empty', noRows, null],
    ['unknown', null, 'unknown', 'non-empty', someRows, null],
    ['own', 'userA', 'this', 'empty', noRows, 'append'],
    ['own', 'userA', 'this', 'non-empty', someRows, 'append'],
  ] as const)('%s owner (%s, %s) over a %s cloud', async (_who, owner, localOwner, _cloud, rows, expected) => {
    const app = await dialogFor(owner, rows)
    expect(app.cloudMerge.value?.localOwner).toBe(localOwner)
    const { defaultMergeChoice } = await import('./useGroupPersistence')
    expect(defaultMergeChoice(app.cloudMerge.value!)).toBe(expected)
    expectNoWrites()
  })

  it('offers keep-cloud only over a cloud that holds something', async () => {
    const { offeredMergeChoices } = await import('./useGroupPersistence')
    const app = await dialogFor(null, someRows)
    expect(offeredMergeChoices(app.cloudMerge.value!.cloudRows)).toContain('keep-cloud')
    expect(offeredMergeChoices([])).not.toContain('keep-cloud')
  })

  it('records the owner on an agreement, not on a deferred prompt', async () => {
    const deferred = await atDialog()
    deferred.resolveMergeCancel()
    expect(localStorage.getItem(OWNER_KEY)).toBeNull()

    const first = await load()
    await first.tryBootstrapCloudSync()
    expect(first.cloudMerge.value?.localOwner).toBe('unknown')
    await first.resolveMergeAppend()
    expect(localStorage.getItem(OWNER_KEY)).toBe('userA')

    localStorage.removeItem(metaKey('userA'))
    signIn('userA', 'sessA2')
    const same = await load()
    await same.tryBootstrapCloudSync()
    expect(same.cloudMerge.value?.localOwner).toBe('this')

    signIn('userB', 'sessB')
    const other = await load()
    await other.tryBootstrapCloudSync()
    expect(other.cloudMerge.value?.localOwner).toBe('other')
  })

  it("a legacy user's newer local stays until they pick: the first sign-in after deploy", async () => {
    await seedLocal()
    localStorage.setItem(metaKey('userA'), JSON.stringify({ f_g_1: { cloudId: 'x', serverUpdatedAt: 't' } }))
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue([cloudRow(app, 'f_g_1', '雲端舊版')])
    await app.tryBootstrapCloudSync()
    const { defaultMergeChoice } = await import('./useGroupPersistence')
    expect(defaultMergeChoice(app.cloudMerge.value!)).toBeNull()
    expect(localNames(app)).toEqual(['自由編組', '庫存編組'])
  })
})

describe('finding 2: hero-less work is work', () => {
  const seedHeroless = (group: string, team: string, extra: object = {}): void => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      v: 5,
      workspaces: {
        free: { active_group_index: 0, groups: [{ id: 'f_g_1', name: group, teams: [{ name: team, ...extra }] }] },
        inventory: { active_group_index: 0, groups: [] },
      },
    }))
  }

  it('over a non-empty cloud: the dialog asks, nothing is replaced', async () => {
    seedHeroless('我的計畫', '自訂隊')
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue([cloudRow(app)])
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).not.toBeNull()
    expect(localNames(app)).toContain('我的計畫')
  })

  it('over an empty cloud: the dialog asks, nothing goes up to B', async () => {
    seedHeroless('A的私人命名', 'A隊名')
    signIn('userB', 'sessB')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).not.toBeNull()
    await editAndPush(app)
    expectNoWrites()
  })

  it('a custom team name alone counts', async () => {
    seedHeroless('預設', 'A隊名')
    signIn('userB', 'sessB')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).not.toBeNull()
  })

  it('a default group with default teams still counts as nothing', async () => {
    seedHeroless('預設', '隊伍 1')
    signIn('userB', 'sessB')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).toBeNull()
  })

  it('a skill chosen on a hero-less slot counts', async () => {
    const { isUntouchedShareableGroup } = await import('../lib/lineupSerialize')
    expect(isUntouchedShareableGroup({ name: '預設', teams: [{ name: '隊伍 1', m_s1: 'x' }] as ShareableGroup['teams'] })).toBe(false)
    expect(isUntouchedShareableGroup({ name: '預設', teams: [{ name: '隊伍 1' }] as ShareableGroup['teams'] })).toBe(true)
  })

  it('an INSERT that found a hero-less row with a chosen name raises a conflict instead of filling it', async () => {
    const app = await atDialog()
    cloud.create.mockImplementation(async (...args: unknown[]) => {
      const input = lastArg<{ client_id: string }>(args)
      return { row: row({ id: input.client_id, name: '別處的計畫', teams: [{ name: '自訂隊' }] } as ShareableGroup), adopted: true }
    })
    await app.resolveMergeAppend()
    await app.flushPendingCloudPush()
    expect(app.cloudConflict.value?.serverRow.name).toBe('別處的計畫')
    expect(cloud.patch).not.toHaveBeenCalled()
  })

  it('keep-local backs up a hero-less cloud row before overwriting the account', async () => {
    const app = await atDialog(() => [row({ id: 'f_g_9', name: '雲端計畫', teams: [{ name: '自訂隊' }] } as ShareableGroup)])
    const res = await app.resolveMergeKeepLocal()
    expect(cloud.share).toHaveBeenCalledTimes(1)
    expect(res.backupSlug).toBe('backupslug00')
  })
})

describe('finding 4: keep-local uploads before it removes anything', () => {
  it('removes nothing and hands back the backup when the upload fails', async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    cloud.bulk.mockRejectedValue(new Error('offline'))
    const res = await app.resolveMergeKeepLocal()
    expect(res).toEqual({ kind: 'cancel', backupSlug: 'backupslug00' })
    expect(cloud.remove).not.toHaveBeenCalled()
    expect(app.cloudMerge.value).not.toBeNull()
    await app.flushPendingCloudPush()
    expect(cloud.remove).not.toHaveBeenCalled()
  })

  it('removes the rows local does not hold only after the upload, each under its lock', async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    const res = await app.resolveMergeKeepLocal()
    expect(res.kind).toBe('keep-local')
    expect(cloud.remove).not.toHaveBeenCalled()
    await app.flushPendingCloudPush()
    expect(cloud.bulk.mock.invocationCallOrder[0]).toBeLessThan(cloud.remove.mock.invocationCallOrder[0])
    expect(cloud.remove.mock.calls[0].slice(-2)).toEqual(['row_f_g_9', '2026-11-07T00:00:00Z'])
  })

  it('overwrites a row local also holds in place, under its lock, without removing it', async () => {
    const app = await atDialog((a) => [cloudRow(a, 'f_g_1', '雲端版本')])
    expect((await app.resolveMergeKeepLocal()).kind).toBe('keep-local')
    await app.flushPendingCloudPush()
    expect(cloud.patch.mock.calls[0].slice(-3, -1)).toEqual(['row_f_g_1', '2026-11-07T00:00:00Z'])
    expect(cloud.remove).not.toHaveBeenCalled()
  })

  it('a retry after a failed upload does not read its own rows as another client moving', async () => {
    const app = await atDialog((a) => [cloudRow(a, 'f_g_1', '雲端版本')])
    cloud.patch.mockResolvedValueOnce({ kind: 'error', message: 'offline' })
    const shown = [cloudRow(app, 'f_g_1', '雲端版本')]
    const created = await cloud.bulk('userA', [{ client_id: 'i_g_1', name: '庫存編組', teams: [] }])
    cloud.bulk.mockClear()
    expect((await app.resolveMergeKeepLocal()).kind).toBe('cancel')
    cloud.list.mockResolvedValue([...shown, ...created])
    expect((await app.resolveMergeKeepLocal()).kind).toBe('keep-local')
  })
})

describe('finding 5: a decision acts on what is there now', () => {
  it.each([
    ['resolveMergeKeepLocal'],
    ['resolveMergeKeepCloud'],
    ['resolveMergeAppend'],
  ] as const)('%s: rows that moved are shown, and decide nothing', async (resolve) => {
    const app = await atDialog((a) => [cloudRow(a)])
    const moved = { ...cloudRow(app), name: '別處改過', updated_at: '2026-11-07T09:00:00Z' }
    cloud.list.mockResolvedValue([moved])
    const res = await app[resolve]()
    expect(res).toEqual({ kind: 'cancel', cloudMoved: true })
    expect(app.cloudMerge.value?.cloudRows[0].name).toBe('別處改過')
    expect(cloud.share).not.toHaveBeenCalled()
    expectNoWrites()
    expect(localNames(app)).toEqual(['自由編組', '庫存編組'])
  })

  it('the next click goes on, with the moved row in the backup', async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    const moved = { ...cloudRow(app), name: '別處改過', updated_at: '2026-11-07T09:00:00Z' }
    cloud.list.mockResolvedValue([moved])
    await app.resolveMergeKeepLocal()
    expect((await app.resolveMergeKeepLocal()).kind).toBe('keep-local')
    const backup = JSON.stringify(cloud.share.mock.calls[0][0])
    expect(backup).toContain('別處改過')
    await app.flushPendingCloudPush()
    expect(cloud.remove.mock.calls[0].slice(-1)).toEqual(['2026-11-07T09:00:00Z'])
  })

  it("a sibling's local save while the dialog is up is in the keep-cloud backup", async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY)!) as ShareableData
    stored.workspaces!.free!.groups![0].name = '另一分頁的編輯'
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
    expect((await app.resolveMergeKeepCloud()).kind).toBe('keep-cloud')
    expect(JSON.stringify(cloud.share.mock.calls[0][0])).toContain('另一分頁的編輯')
  })

  it("closes on a sibling's decision and takes in what it decided, deleting nothing", async () => {
    const second = await atDialog((a) => [cloudRow(a)])
    const first = await load()
    await first.tryBootstrapCloudSync()
    expect(first.cloudMerge.value).not.toBeNull()
    expect((await first.resolveMergeAppend()).kind).toBe('append')

    vi.clearAllMocks()
    const res = await second.resolveMergeKeepLocal()
    expect(res.kind).toBe('cancel')
    expect(second.cloudMerge.value).toBeNull()
    expect(cloud.share).not.toHaveBeenCalled()
    await second.flushPendingCloudPush()
    expect(cloud.remove).not.toHaveBeenCalled()
    expect(cloud.bulk).not.toHaveBeenCalled()
    expect(localNames(second)).toContain('雲端編組')
  })

  it("closes on a sibling's saved message without waiting for a click", async () => {
    const second = await atDialog((a) => [cloudRow(a)])
    second.enableAutosave()
    const first = await load()
    await first.tryBootstrapCloudSync()
    first.enableAutosave()
    await first.resolveMergeAppend()
    await vi.waitFor(() => expect(second.cloudMerge.value).toBeNull())
  })
})

describe('the bootstrap itself', () => {
  it('a persisted event of the same session leaves an open dialog and its snapshot alone', async () => {
    await seedLocal()
    signIn('userA', 'sessA')
    const app = await load()
    app.enableAutosave()
    await app.tryBootstrapCloudSync()
    const shown = app.cloudMerge.value
    expect(shown).not.toBeNull()
    app.auth.handleAuthCallback(`#access_token=${jwt('userA', 'sessA')}&refresh_token=r2&expires_in=3600`)
    await vi.advanceTimersByTimeAsync(5)
    expect(cloud.list).toHaveBeenCalledTimes(1)
    expect(app.cloudMerge.value).toBe(shown)
  })

  it('a team entry that is not a team does not reach the dialog, nor leave the bootstrap stuck', async () => {
    await seedLocal()
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue([{ id: 'bad', client_id: 'bad', name: 'x', teams: [null] }])
    await expect(app.tryBootstrapCloudSync()).resolves.toBeUndefined()
    expect(app.cloudStatus.value).toBe('error')
    expect(app.cloudMerge.value).toBeNull()
    expectNoWrites()

    cloud.list.mockResolvedValue([cloudRow(app)])
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).not.toBeNull()
  })

  it('a team entry that arrives at decision time leaves the open dialog as it was', async () => {
    const app = await atDialog((a) => [cloudRow(a)])
    const shown = app.cloudMerge.value!.cloudRows
    cloud.list.mockResolvedValue([{ ...cloudRow(app), updated_at: 'later', teams: [null] }])
    expect((await app.resolveMergeKeepLocal()).kind).toBe('cancel')
    expect(app.cloudMerge.value!.cloudRows).toEqual(shown)
    expect(cloud.share).not.toHaveBeenCalled()
    expectNoWrites()
  })
})

describe('nothing local', () => {
  it('prompts for nothing and writes nothing', async () => {
    signIn('userA', 'sessA')
    const app = await load()
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).toBeNull()
    expectNoWrites()
  })

  it('applies a non-empty cloud over an empty local without a dialog', async () => {
    signIn('userA', 'sessA')
    const app = await load()
    cloud.list.mockResolvedValue(localGroups(app).map(row))
    await app.tryBootstrapCloudSync()
    expect(app.cloudMerge.value).toBeNull()
    expect(app.useGroups().workspaces.free.groups[0].name).toBe('自由編組')
    expectNoWrites()
  })
})
