import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fingerprint, hmacKey, Invalid, nameHmac, parseBattle, parseHeader, prepare } from './core.ts'

const hero = (cfg_id: number | null = 101) => ({ cfg_id, name: '織田信長', level: 50, red: 5 })

function side(hp: number | null, extra: Record<string, unknown> = {}) {
  return {
    role: 'attack', player: 'Ｐｌａｙｅｒ ', alliance: '盟', troop_type: '騎兵', troop_lv: 10,
    hp, hp_max: 10000, wounded: 100, dead: 50, heroes: [hero(), hero(102), hero(null)], ...extra,
  }
}

function battle(seq: number, l = side(9000), r = side(8000)) {
  return { seq, level: 'list', date: '2026-10-27 21:05:33', result: 'win', coord: { x: 512, y: 300 }, left: l, right: r }
}

function body(battles: unknown[], extra: Record<string, unknown> = {}) {
  return {
    schema_version: 3, client_version: '0.1.0', ocr_model: 'ppocr-v6-rec', consent_version: '1', edition: 'tw',
    server: 'S00012', session_id: '7d4f2c1e-9b8a-4c3d-8e2f-1a2b3c4d5e6f', captured_at: '2026-10-27T13:10:00Z',
    anonymous: false, battles, ...extra,
  }
}

const anon = (s: Record<string, unknown>) => {
  const { player: _p, alliance: _a, ...rest } = s
  return rest
}

const key = () => hmacKey('test-secret')

test('a valid upload is accepted with names moved to identities', async () => {
  const out = await prepare(body([battle(0)]), await key())
  assert.deepEqual(out.rejected, [])
  assert.equal(out.rows.length, 1)
  const row = out.rows[0] as Record<string, any>
  assert.equal('player' in row.left, false)
  assert.equal(row.identities.left.player_raw, 'Player') // NFKC + trimmed
  assert.match(row.identities.left.player_hmac, /^[0-9a-f]{64}$/)
  assert.equal(row.mirrored, true) // left 9000 sorts after right 8000
})

test('header: unknown key, wrong schema, bad edition / server / session are 400', () => {
  const bad = [
    body([battle(0)], { image: 'data:' }),
    body([battle(0)], { schema_version: 2 }),
    body([battle(0)], { edition: 'jp' }),
    body([battle(0)], { server: 'S 1' }),
    body([battle(0)], { session_id: 'nope' }),
    body([battle(0)], { captured_at: '27/10/2026' }),
    body([]),
    body(Array.from({ length: 201 }, (_, i) => battle(i))),
  ]
  for (const b of bad) assert.throws(() => parseHeader(b), Invalid)
})

test('anonymous: identity keys anywhere reject the batch; absent keys pass', async () => {
  const leaked = body([battle(0, anon(side(9000)) as any, anon(side(8000)) as any), battle(1, anon(side(9000)) as any)], { anonymous: true })
  assert.throws(() => parseHeader(leaked), /anonymous/)
  const nulls = body([battle(0, { ...anon(side(9000)), player: null } as any, anon(side(8000)) as any)], { anonymous: true })
  assert.throws(() => parseHeader(nulls), /anonymous/)
  const clean = body([battle(0, anon(side(9000)) as any, anon(side(8000)) as any)], { anonymous: true })
  const out = await prepare(clean, await key())
  assert.equal(out.rows.length, 1)
  assert.equal(out.rows[0].identities, null)
})

test('per-battle checks reject the battle, not the batch', async () => {
  const cases: [unknown, RegExp][] = [
    [{ ...battle(1), raw_text: 'x' }, /unknown key/],
    [battle(2, side(9000, { ocr: 'x' })), /unknown key/],
    [battle(3, side(9000, { heroes: [hero(), hero()] })), /3 heroes/],
    [battle(4, side(9000, { heroes: [hero(), hero(), { ...hero(), level: 51 }] })), /level/],
    [battle(5, side(9000, { heroes: [hero(), hero(), { ...hero(), red: 6 }] })), /red/],
    [battle(6, side(10001)), /above hp_max/],
    [battle(7, side(-1)), /hp/],
    [battle(8, side(9000, { troop_lv: 1.5 })), /troop_lv/],
    [battle(9, side(9000, { troop_type: '水軍' })), /troop_type/],
    [{ ...battle(10), date: '2026-02-30 10:00:00' }, /calendar/],
    [{ ...battle(11), date: '2026/10/27 10:00:00' }, /YYYY/],
    [{ ...battle(12), level: 'brief' }, /level/],
    [{ ...battle(13), result: 'won' }, /result/],
  ]
  const out = await prepare(body([battle(0), ...cases.map((c) => c[0]), battle(0)]), await key())
  assert.equal(out.rows.length, 1)
  cases.forEach(([, re], k) => assert.match(out.rejected[k].reason, re, `case ${k}`))
  assert.deepEqual(out.rejected.at(-1), { index: cases.length + 1, reason: 'seq: duplicate in payload' })
})

test('nulls are allowed where the client may leave a field unread', () => {
  const s = side(null, { role: null, troop_type: null, troop_lv: null, heroes: [{ cfg_id: null, name: null, level: null, red: null }, hero(), hero()] })
  const b = parseBattle({ ...battle(0, s), date: null, result: null, coord: null }, false)
  assert.equal(b.left.hp, null)
  assert.deepEqual(fingerprint(b), { fp: null, mirrored: false })
})

test('a mirrored upload has the same fp, flagged mirrored', () => {
  const a = parseBattle(battle(0, side(9000), side(8000)), false)
  const m = parseBattle(battle(0, side(8000), side(9000)), false)
  const fa = fingerprint(a)
  const fm = fingerprint(m)
  assert.ok(fa.fp)
  assert.equal(fa.fp, fm.fp)
  assert.equal(fa.mirrored !== fm.mirrored, true)
  assert.equal(fa.fp, '2026-10-27 21:05:33|512,300|8000|10000|100|50|9000|10000|100|50')
})

test('fp is null when the date, the coord or any troop number is unread', () => {
  assert.equal(fingerprint(parseBattle({ ...battle(0), date: null }, false)).fp, null)
  assert.equal(fingerprint(parseBattle(battle(0, side(9000, { dead: null })), false)).fp, null)
  assert.equal(fingerprint(parseBattle({ ...battle(0), coord: null }, false)).fp, null)
})

test('hmac is stable and keyed', async () => {
  const k = await key()
  assert.equal(await nameHmac(k, 'A'), await nameHmac(k, 'A'))
  assert.notEqual(await nameHmac(k, 'A'), await nameHmac(await hmacKey('other'), 'A'))
  assert.equal(await nameHmac(k, null), null)
})
