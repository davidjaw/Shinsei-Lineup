import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const session = (user: string) => JSON.stringify({
  access_token: `h.${btoa(JSON.stringify({ sub: user }))}.s`,
  refresh_token: 'r',
  expires_at: Math.floor(Date.now() / 1000) + 3600,
  user: { id: user, email: `${user}@mail.test`, display_name: null },
})
const signIn = (user: string): void => localStorage.setItem('nobunaga.auth.session', session(user))

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

const loadModules = async () => {
  vi.resetModules()
  vi.stubEnv('VITE_SUPABASE_URL', 'https://stub.test')
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'stub-key')
  return { lib: await import('./lineupGroups'), auth: await import('./auth') }
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('a call bound to an account', () => {
  it.each(['list', 'create', 'bulk', 'patch', 'force', 'remove'])('%s sends nothing once another account is signed in', async (name) => {
    const fetchMock = vi.fn(async () => answer([]))
    vi.stubGlobal('fetch', fetchMock)
    signIn('userB')
    const { lib, auth } = await loadModules()
    const input = { client_id: 'c', name: 'n', teams: [] }
    const calls: Record<string, () => Promise<unknown>> = {
      list: () => lib.listMyLineupGroups('userA'),
      create: () => lib.createLineupGroup('userA', input),
      bulk: () => lib.bulkCreateLineupGroups('userA', [input]),
      patch: () => lib.patchLineupGroupWithLock('userA', 'id', 't', input),
      force: () => lib.patchLineupGroupForce('userA', 'id', input),
      remove: () => lib.deleteLineupGroup('userA', 'id', 't'),
    }
    await expect(calls[name]()).rejects.toBeInstanceOf(auth.AccountChangedError)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('a bulk retry stops at the first row after the account changed', async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => {
      signIn('userB')
      return answer({}, 409)
    })
    vi.stubGlobal('fetch', fetchMock)
    signIn('userA')
    const { lib, auth } = await loadModules()
    const inputs = [{ client_id: 'c1', name: 'a', teams: [] }, { client_id: 'c2', name: 'b', teams: [] }]
    await expect(lib.bulkCreateLineupGroups('userA', inputs)).rejects.toBeInstanceOf(auth.AccountChangedError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('a 0-row PATCH does not read another account as a deleted row', async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => {
      signIn('userB')
      return answer([])
    })
    vi.stubGlobal('fetch', fetchMock)
    signIn('userA')
    const { lib, auth } = await loadModules()
    await expect(lib.patchLineupGroupWithLock('userA', 'id', 't', { name: 'n', teams: [] })).rejects.toBeInstanceOf(auth.AccountChangedError)
  })
})

describe('deleteLineupGroup', () => {
  it('names the version the caller saw', async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    signIn('userA')
    const { lib } = await loadModules()
    await lib.deleteLineupGroup('userA', 'row1', '2026-11-07T00:00:00Z')
    expect(fetchMock.mock.calls[0][0]).toBe('https://stub.test/rest/v1/lineup_groups?id=eq.row1&updated_at=eq.2026-11-07T00%3A00%3A00Z')
  })
})
