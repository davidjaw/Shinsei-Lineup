import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CONSENT_VERSION, fingerprint, hmacKey, Invalid, nameHmac, parseBattle, parseHeader, prepare, readBody } from './core.ts'

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
    schema_version: 3, client_version: '0.1.0', ocr_model: 'ppocr-v6-rec', consent_version: CONSENT_VERSION, edition: 'tw',
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
  assert.match(row.identities.left.player_hmac, /^[0-9a-f]{64}$/)
  assert.equal('player_raw' in row.identities.left, false) // names are never stored, only their HMACs
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
    [{ ...battle(12), level: 'brief' }, /cards: missing/],
    [{ ...battle(14), level: 'raw' }, /level/],
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
  assert.deepEqual(fingerprint(b), { fp: null, nums: null, mirrored: false })
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

// ---- brief (總覽) battles ----

const skill = (name: string, grade: string | null = 'S') => ({ grade, name, launch: 3, kills: 2457, rescue: 0 })
const card = (k: number, h = hero()) => ({
  ...h, team: k < 3 ? 'blue' : 'red', pos: (k % 3) + 1, commander: k === 0, routed: false, troops: 8670,
  skills: [skill('伊達風采'), skill('龍騎兵'), skill('攻其不備'), skill('普通攻擊', 'A')],
})
const empty = (k: number) => ({
  cfg_id: null, name: null, level: null, red: null, team: k < 3 ? 'blue' : 'red', pos: (k % 3) + 1,
  commander: false, routed: false, troops: null, skills: [],
})

/** A brief whose sides' heroes are its cards' (the third red slot empty). */
function brief(seq: number, edit: (cards: any[]) => void = () => {}) {
  const heroes = [hero(), hero(102), hero(null)]
  const cards: any[] = [...heroes.map((h, k) => card(k, h)), card(3), card(4, hero(102)), empty(5)]
  edit(cards)
  const r = side(8000, { heroes: [hero(), hero(102), { cfg_id: null, name: null, level: null, red: null }] })
  return { ...battle(seq, side(9000), r), level: 'brief', cards }
}

test('a valid brief is accepted; its fp equals the list row of the same seq', async () => {
  const out = await prepare(body([battle(0), brief(0)]), await key())
  assert.deepEqual(out.rejected, [])
  const [list, b] = out.rows as Record<string, any>[]
  assert.equal('cards' in list, false)
  assert.equal(b.cards.length, 6)
  assert.deepEqual(b.cards[5].skills, [])
  assert.equal(b.cards[3].skills[3].grade, 'A')
  assert.equal(b.fp, list.fp)
  assert.equal(b.level, 'brief')
})

test('brief checks reject the battle with a field path', async () => {
  const cases: [unknown, RegExp][] = [
    [brief(1, (c) => c.pop()), /^cards: 6 cards expected$/],
    [{ ...battle(2), cards: brief(2).cards }, /^cards: brief battles only$/],
    [brief(3, (c) => { c[0].skills.push(skill('x')) }), /^cards\[0\]\.skills: 0\.\.4/],
    [brief(4, (c) => { c[1].skills[0].grade = 'C' }), /^cards\[1\]\.skills\[0\]\.grade: one of S\/A\/B/],
    [brief(5, (c) => { c[1].skills[0].grade = '' }), /grade/],
    [brief(6, (c) => { c[0].team = 'red' }), /^cards\[0\]\.team: blue expected$/],
    [brief(7, (c) => { c[4].pos = 1 }), /^cards\[4\]\.pos: 2 expected$/],
    [brief(8, (c) => { c[2].red = 6 }), /^cards\[2\]\.red/],
    [brief(9, (c) => { c[2].level = 0 }), /^cards\[2\]\.level/],
    [brief(10, (c) => { c[3].skills[0].ocr = 'raw' }), /^cards\[3\]\.skills\[0\]: unknown key$/],
    [brief(11, (c) => { c[3].flags = [] }), /^cards\[3\]: unknown key$/],
    [brief(12, (c) => { c[3].routed = 'yes' }), /routed: boolean/],
    [brief(13, (c) => { c[1].commander = true }), /more than one commander/],
    [brief(14, (c) => { c[4].level = 49 }), /^right\.heroes\[1\]: differs from cards\[4\]$/],
    [brief(15, (c) => { c[0].skills[0].kills = -1 }), /kills/],
    [brief(16, (c) => { c[0].troops = 100001 }), /^cards\[0\]\.troops/],
    [brief(17, (c) => { c[0].skills[0].launch = 201 }), /launch/],
  ]
  const out = await prepare(body(cases.map((c) => c[0])), await key())
  assert.equal(out.rows.length, 0)
  cases.forEach(([, re], k) => assert.match(out.rejected[k].reason, re, `case ${k}`))
})

test('brief: nulls where unread, no skills on any card', () => {
  const b = parseBattle(brief(0, (c) => {
    c[0] = { ...c[0], routed: null, troops: null, skills: [{ grade: null, name: null, launch: null, kills: null, rescue: null }] }
    c[1].skills = []
  }), false)
  assert.equal(b.cards![0].routed, null)
  assert.equal(b.cards![1].skills.length, 0)
})

test('brief anonymous: identity keys on its sides reject the batch; clean sides pass', async () => {
  const leaked = body([brief(0)], { anonymous: true })
  assert.throws(() => parseHeader(leaked), /anonymous/)
  const b = brief(0)
  const clean = body([{ ...b, left: anon(b.left), right: anon(b.right) }], { anonymous: true })
  const out = await prepare(clean, await key())
  assert.deepEqual(out.rejected, [])
  assert.equal(out.rows[0].identities, null)
})

test('a mirrored brief has the same fp', () => {
  const a = parseBattle(brief(0), false)
  const b = brief(0)
  const m = parseBattle({ ...b, left: b.right, right: b.left, cards: [...b.cards.slice(3), ...b.cards.slice(0, 3)].map((c, k) => ({ ...c, team: k < 3 ? 'blue' : 'red' })) }, false)
  assert.equal(fingerprint(a).fp, fingerprint(m).fp)
  assert.notEqual(fingerprint(a).mirrored, fingerprint(m).mirrored)
})

test('a brief and a list battle may share a seq; two briefs may not', async () => {
  const out = await prepare(body([battle(0), brief(0), brief(0)]), await key())
  assert.equal(out.rows.length, 2)
  assert.deepEqual(out.rejected, [{ index: 2, reason: 'seq: duplicate in payload' }])
})

// ---- review fixes ----

test('unknown keys are reported by path only, never echoing the key', async () => {
  const out = await prepare(body([{ ...battle(0), 'DROP TABLE x; --': 1 }, battle(1, side(9000, { ['k'.repeat(500)]: 1 }))]), await key())
  assert.deepEqual(out.rejected.map((r) => r.reason), ['battle: unknown key', 'left: unknown key'])
})

test('consent_version: only the current notice is accepted', () => {
  assert.equal(parseHeader(body([battle(0)])).header.consent_version, CONSENT_VERSION)
  for (const v of ['1', '2026-10-27', '', null]) {
    assert.throws(() => parseHeader(body([battle(0)], { consent_version: v })), /consent_version/)
  }
})

test('side numbers: bounded, wounded + dead within hp_max', async () => {
  const ok = [side(31500, { hp_max: 36000, wounded: 19235, dead: 0, troop_lv: 12 }), side(0, { hp_max: 30267, wounded: 10641, dead: 16545 })]
  for (const s of ok) assert.ok(parseBattle(battle(0, s), false))
  const cases: [unknown, RegExp][] = [
    [battle(1, side(9000, { hp_max: 100001 })), /^left\.hp_max/],
    [battle(2, side(9000, { troop_lv: 51 })), /^left\.troop_lv/],
    [battle(3, side(9000, { dead: 100001 })), /^left\.dead/],
    [battle(4, side(9000, { wounded: 6000, dead: 4001 })), /^left: wounded \+ dead above hp_max$/],
  ]
  const out = await prepare(body(cases.map((c) => c[0])), await key())
  assert.equal(out.rows.length, 0)
  cases.forEach(([, re], k) => assert.match(out.rejected[k].reason, re, `case ${k}`))
  // Unread numbers skip the sum check.
  assert.ok(parseBattle(battle(5, side(9000, { hp_max: null, wounded: 90000, dead: 90000 })), false))
})

test('heroes: cfg_id range, cfg_id needs a name, names are bounded letters', async () => {
  const h = (extra: Record<string, unknown>) => battle(0, side(9000, { heroes: [hero(), hero(), { ...hero(), ...extra }] }))
  assert.ok(parseBattle(h({ cfg_id: 12019, name: '甲斐弓騎兵·拓' }), false))
  const cases: [unknown, RegExp][] = [
    [h({ cfg_id: 0 }), /^left\.heroes\[2\]\.cfg_id: integer 1\.\.99999/],
    [h({ cfg_id: 100000 }), /cfg_id/],
    [h({ name: null }), /^left\.heroes\[2\]\.cfg_id: without a name$/],
    [h({ name: 'http://x.io' }), /^left\.heroes\[2\]\.cfg_id: without a name$/],
    [h({ name: 42 }), /name: string expected/],
  ]
  const out = await prepare(body(cases.map((c, k) => ({ ...(c[0] as object), seq: k }))), await key())
  assert.equal(out.rows.length, 0)
  cases.forEach(([, re], k) => assert.match(out.rejected[k].reason, re, `case ${k}`))
  // Without a cfg_id, an overlong or odd name is dropped and the battle kept.
  for (const name of ['織田'.repeat(9), 'http://x.io', '<b>x</b>']) {
    assert.equal(parseBattle(h({ cfg_id: null, name }), false).left.heroes[2].name, null, name)
  }
})

test('names: NFKC, then control / format characters dropped, then trimmed and length-checked', async () => {
  const named = (player: string) => battle(0, side(9000, { player }))
  const row = async (player: string) => (await prepare(body([named(player)]), await key())).rows[0] as Record<string, any>
  const hmac = async (name: string) => nameHmac(await key(), name)
  assert.equal((await row('\u200bＡ\u0007b\u202e ')).identities.left.player_hmac, await hmac('Ab'))
  assert.equal((await row('\u200b\u200b')).identities.left.player_hmac, null)
  // U+FDFA is one code unit but 18 after NFKC: 4 of them pass the raw length, not the normalised one.
  const out = await prepare(body([named('\uFDFA'.repeat(4))]), await key())
  assert.match(out.rejected[0].reason, /^left\.player: at most 64/)
  // The game-name charset applies after normalisation: a full-width letter is a letter, a zero-width space is gone.
  assert.ok(parseBattle(battle(0, side(9000, { heroes: [hero(), hero(), { ...hero(), name: '織\u200b田' }] })), false))
})

test('readBody: stops at the cap with or without Content-Length', async () => {
  const stream = (n: number) => new ReadableStream<Uint8Array>({
    start(c) { for (let i = 0; i < n; i++) c.enqueue(new Uint8Array(10).fill(65)); c.close() },
  })
  const req = (n: number, headers: Record<string, string> = {}) =>
    new Request('http://x/', { method: 'POST', body: stream(n), headers, duplex: 'half' } as RequestInit)
  assert.equal(await readBody(req(10), 100), 'A'.repeat(100))
  assert.equal(await readBody(req(11), 100), null)
  assert.equal(await readBody(req(1, { 'content-length': '101' }), 100), null)
  assert.equal(await readBody(new Request('http://x/', { method: 'POST', body: '{"a":"é"}' })), '{"a":"é"}')
})

test('fingerprint: nums are the canonical eight; equal side keys order by role, attacker first', () => {
  const a = parseBattle(battle(0, side(9000), side(8000)), false)
  assert.deepEqual(fingerprint(a).nums, [8000, 10000, 100, 50, 9000, 10000, 100, 50])
  const tie = (l: string, r: string) => parseBattle(battle(0, side(9000, { role: l }), side(9000, { role: r })), false)
  assert.equal(fingerprint(tie('defend', 'attack')).mirrored, true)
  assert.equal(fingerprint(tie('attack', 'defend')).mirrored, false)
  assert.equal(fingerprint(tie('attack', 'defend')).fp, fingerprint(tie('defend', 'attack')).fp)
})
