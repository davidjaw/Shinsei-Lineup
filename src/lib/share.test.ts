import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const SLUG = 'AbCdEf123456'
const encode = (data: unknown): string => btoa(unescape(encodeURIComponent(JSON.stringify(data))))

const loadModule = async () => {
  vi.resetModules()
  vi.stubEnv('VITE_SUPABASE_URL', 'https://stub.test')
  vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', 'stub-key')
  return import('./share')
}

const answer = (body: unknown, status = 200) =>
  vi.fn(async (..._args: unknown[]) => new Response(JSON.stringify(body), { status }))

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('parseShareInput', () => {
  // The new site's inventory share: JP keys, no `v`, and a blob that holds non-ASCII text.
  const inventory = { inv_h: ['織田信長'], inv_s: ['天下布武'] }
  const b64 = encode(inventory)
  // Base64 with `+` and `/`, which the new site percent-encodes in `/lineup/b/`.
  const awkward = encode({ inv_h: ['>>>???'], inv_s: ['ÿÿÿ~~~'] })

  it.each([
    ['a bare slug', SLUG],
    ['the old form', `https://old.example/#s/${SLUG}`],
    ['the old form after the router rewrite', `https://old.example/#/s/${SLUG}`],
    ['the new site slug link', `https://new.example/#/lineup/s/${SLUG}`],
    ['a new site slug link with a query', `https://new.example/#/lineup/s/${SLUG}?x=1`],
    ['a path-shaped slug link', `https://new.example/lineup/s/${SLUG}`],
  ])('reads %s as a slug', async (_label, text) => {
    const { parseShareInput } = await loadModule()
    expect(parseShareInput(`  ${text} `)).toEqual({ slug: SLUG })
  })

  it.each([
    ['the old form', `https://old.example/#${b64}`],
    ['the old form after the router rewrite', `https://old.example/#/${b64}`],
    ['the new site blob link', `https://new.example/#/lineup/b/${encodeURIComponent(b64)}`],
  ])('reads %s as a blob', async (_label, text) => {
    const { parseShareInput } = await loadModule()
    expect(parseShareInput(text)).toEqual({ base64: b64 })
  })

  it('undoes the percent-encoding of base64 punctuation', async () => {
    const { parseShareInput, decodeShareBlob } = await loadModule()
    const encoded = encodeURIComponent(awkward)
    expect(encoded).not.toBe(awkward)
    const source = parseShareInput(`https://new.example/#/lineup/b/${encoded}`)
    expect(source).toEqual({ base64: awkward })
    expect(decodeShareBlob(awkward)).toEqual({ inv_h: ['>>>???'], inv_s: ['ÿÿÿ~~~'] })
  })

  it.each(['', '   ', 'hello', 'https://new.example/#/lineup', `https://new.example/#/gacha/${SLUG}`, 'https://new.example/#/lineup/b/not-a-blob'])(
    'rejects %j',
    async (text) => {
      const { parseShareInput } = await loadModule()
      expect(parseShareInput(text)).toBeNull()
    },
  )
})

describe('loadShareSource', () => {
  it('imports the inventory of a new-site blob link without a request', async () => {
    const fetchMock = answer(null)
    vi.stubGlobal('fetch', fetchMock)
    const { loadShareSource } = await loadModule()
    const inventory = { inv_h: ['織田信長'], inv_s: ['天下布武'] }
    await expect(loadShareSource(`https://new.example/#/lineup/b/${encodeURIComponent(encode(inventory))}`)).resolves.toEqual(inventory)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('imports the inventory of a new-site slug link through the RPC', async () => {
    const inventory = { inv_h: ['織田信長'], inv_s: [] }
    vi.stubGlobal('fetch', answer(inventory))
    const { loadShareSource } = await loadModule()
    await expect(loadShareSource(`https://new.example/#/lineup/s/${SLUG}`)).resolves.toEqual(inventory)
  })

  it('answers null for text that points at nothing', async () => {
    const { loadShareSource } = await loadModule()
    await expect(loadShareSource('hello')).resolves.toBeNull()
  })
})

describe('loadShare', () => {
  it('reads through the share_blob RPC', async () => {
    const blob = { v: 2, inv_h: ['織田信長'] }
    const fetchMock = answer(blob)
    vi.stubGlobal('fetch', fetchMock)
    const { loadShare } = await loadModule()
    await expect(loadShare(SLUG)).resolves.toEqual(blob)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('https://stub.test/rest/v1/rpc/share_blob')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ p_slug: SLUG })
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('takes NULL for an unknown slug', async () => {
    vi.stubGlobal('fetch', answer(null))
    const { loadShare } = await loadModule()
    await expect(loadShare(SLUG)).rejects.toThrow('share not found')
  })

  it('reports a failing RPC, and sends nothing for a malformed slug', async () => {
    const fetchMock = answer({ message: 'nope' }, 404)
    vi.stubGlobal('fetch', fetchMock)
    const { loadShare } = await loadModule()
    await expect(loadShare(SLUG)).rejects.toThrow('share load failed: 404')
    fetchMock.mockClear()
    await expect(loadShare('short')).rejects.toThrow('invalid share slug')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
