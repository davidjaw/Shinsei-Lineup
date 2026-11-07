import { afterEach, describe, expect, it, vi } from 'vitest'
import { AUTHOR_NAME_MAX, publicAuthorName } from './displayName'

describe('publicAuthorName', () => {
  it('passes a chosen name, capped', () => {
    expect(publicAuthorName(' 信長 ', 'someone@mail.test')).toBe('信長')
    expect(publicAuthorName('x'.repeat(40), 'someone@mail.test')).toHaveLength(AUTHOR_NAME_MAX)
    expect(publicAuthorName('信長', undefined)).toBe('信長')
  })

  it('refuses the email prefix, whatever its case or cap', () => {
    expect(publicAuthorName('someone', 'someone@mail.test')).toBeNull()
    expect(publicAuthorName('SomeOne', 'someone@mail.test')).toBeNull()
    const long = 'y'.repeat(40)
    expect(publicAuthorName(long.slice(0, AUTHOR_NAME_MAX), `${long}@mail.test`)).toBeNull()
  })

  it('has nothing for no name', () => {
    expect(publicAuthorName(null, 'someone@mail.test')).toBeNull()
    expect(publicAuthorName('   ', 'someone@mail.test')).toBeNull()
    expect(publicAuthorName(undefined, undefined)).toBeNull()
  })
})

describe('what leaves the client', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  const signedIn = async (display_name: string | null) => {
    vi.resetModules()
    vi.stubEnv('VITE_SUPABASE_URL', 'https://stub.test')
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'stub-key')
    localStorage.setItem('nobunaga.auth.session', JSON.stringify({
      access_token: `h.${btoa(JSON.stringify({ sub: 'u', email: 'someone@mail.test' }))}.s`,
      refresh_token: 'r',
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      user: { id: 'u', email: 'someone@mail.test', display_name },
    }))
    const fetchMock = vi.fn(async (..._args: unknown[]) => new Response('[{"id":"p","team_blob":null}]'))
    vi.stubGlobal('fetch', fetchMock)
    const sentBody = (): Record<string, unknown> => JSON.parse((fetchMock.mock.lastCall![1] as RequestInit).body as string)
    return { sentBody }
  }

  it('useAuth has no name from the email, and asks for one', async () => {
    await signedIn(null)
    const { useAuth } = await import('../composables/useAuth')
    expect(useAuth().displayName.value).toBe('')
    expect(useAuth().needsDisplayName.value).toBe(true)
  })

  it('useAuth does not take a saved email prefix for a chosen name', async () => {
    await signedIn('someone')
    const { useAuth } = await import('../composables/useAuth')
    expect(useAuth().displayName.value).toBe('')
    expect(useAuth().needsDisplayName.value).toBe(true)
  })

  it('useAuth keeps a chosen name', async () => {
    await signedIn('信長')
    const { useAuth } = await import('../composables/useAuth')
    expect(useAuth().displayName.value).toBe('信長')
    expect(useAuth().needsDisplayName.value).toBe(false)
  })

  it('a stored email prefix is not sent with a new proposal or a variant', async () => {
    const { sentBody } = await signedIn(null)
    const { createProposal } = await import('./proposals')
    await createProposal({ name: 'n', team: {} as never, isPublic: true, authorName: 'someone' })
    expect(sentBody().author_name).toBeNull()

    const { submitVariant } = await import('./variants')
    await submitVariant({} as never, 'someone').catch(() => {})
    expect(sentBody().p_author_name).toBeNull()
  })

  it('a flip to public writes the author afresh', async () => {
    const { sentBody } = await signedIn('信長')
    const { updateProposal } = await import('./proposals')
    await updateProposal('p', { isPublic: true })
    expect(sentBody().author_name).toBe('信長')
    await updateProposal('p', { name: '新名' })
    expect(sentBody()).not.toHaveProperty('author_name')
  })
})
