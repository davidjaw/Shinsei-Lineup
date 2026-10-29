// Pure logic of capture-ingest: the body size cap, payload validation, name normalisation, HMAC and the dedup fingerprint.
// No Deno APIs here (Web Crypto and Request only), so node can run the tests: npx tsx --test supabase/functions/capture-ingest/*.test.ts

export const SCHEMA_VERSION = 3
export const MAX_BATTLES = 200
// 200 brief battles from real 總覽 reads measure up to ~650 KB (~3.3 KB each, six cards with skills); list battles ~1 KB.
export const MAX_BODY_BYTES = 1024 * 1024
/**
 * The privacy notice version the client consents to (capture/client/src/config.ts UPLOAD.consentVersion). Only this
 * one is accepted, so a notice bump deploys the function first, then the client.
 */
export const CONSENT_VERSION = '2026-10-29'

// Value sets of the capture client (capture/client/src/prefs.ts, cv/listParse.ts, cv/troopIcon.ts, cv/listPixels.ts)
// and of the 總覽 (brief) read: six cards in screen order, left three blue, right three red; a skill column is 固有,
// the learned 戰法 (none, one or two), 普通攻擊, so 2..4 blocks, and an empty slot has none.
const EDITIONS = ['tw', 'hk']
const SERVER_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/
const RESULTS = ['win', 'loss', 'draw']
const ROLES = ['attack', 'defend']
const LEVELS = ['list', 'brief']
const GRADES = ['S', 'A', 'B']
const CARDS = 6
const MAX_SKILLS = 4
const TROOP_TYPES = ['足輕', '弓兵', '騎兵', '鐵炮', '攻城車']
const HERO_LEVEL: [number, number] = [1, 50]
const RED_MAX = 5
const HEROES_PER_SIDE = 3
// Bounds from real reads (14.5k sides, 2.1k cards; max seen: hp 31500, hp_max 36000, wounded 19235, dead 23678,
// troop_lv 12, card troops 10487, launch 39, kills 30134, rescue 12594), with generous headroom.
const TROOPS_MAX = 100000
const TROOP_LV: [number, number] = [0, 50]
const LAUNCH_MAX = 200
// Hero cfg_ids are five digits (10001..12019 today). The server has no lexicon, so cfg_id and name are not
// cross-checked here; the merge job can join them against the hero table.
const CFG_ID: [number, number] = [1, 99999]

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/
const MAX_NAME = 64
/** Hero and skill names (lexicon names, at most 7 characters, CJK / kana plus a middle dot). */
const MAX_GAME_NAME = 16
const GAME_NAME_RE = /^[\p{L}\p{M}\p{N}·・]+$/u
const INVISIBLE_RE = /[\p{Cc}\p{Cf}]/gu
const MAX_LABEL = 64
/** Postgres int4: seq and coordinates are int columns. */
const INT4_MAX = 2147483647

const HEADER_KEYS = [
  'schema_version', 'client_version', 'ocr_model', 'consent_version', 'edition', 'server',
  'session_id', 'captured_at', 'anonymous', 'battles',
]
const BATTLE_KEYS = ['seq', 'level', 'date', 'result', 'coord', 'left', 'right']
const BRIEF_KEYS = [...BATTLE_KEYS, 'cards']
const SIDE_KEYS = ['role', 'troop_type', 'troop_lv', 'hp', 'hp_max', 'wounded', 'dead', 'heroes']
const IDENTITY_KEYS = ['player', 'alliance']
const HERO_KEYS = ['cfg_id', 'name', 'level', 'red']
const CARD_KEYS = [...HERO_KEYS, 'team', 'pos', 'commander', 'routed', 'troops', 'skills']
const SKILL_KEYS = ['grade', 'name', 'launch', 'kills', 'rescue']
const SIDE_NUMBERS = ['hp', 'hp_max', 'wounded', 'dead'] as const

export class Invalid extends Error {}

export interface Hero {
  cfg_id: number | null
  name: string | null
  level: number | null
  red: number | null
}

export interface Side {
  role: string | null
  troop_type: string | null
  troop_lv: number | null
  hp: number | null
  hp_max: number | null
  wounded: number | null
  dead: number | null
  heroes: Hero[]
}

export interface Skill {
  grade: string | null
  name: string | null
  launch: number | null
  kills: number | null
  rescue: number | null
}

/** One 總覽 card. `team` / `pos` are fixed by its place (index k: blue for k < 3, pos k % 3 + 1). */
export interface Card extends Hero {
  team: string
  pos: number
  commander: boolean
  routed: boolean | null
  troops: number | null
  skills: Skill[]
}

export interface Identity {
  player: string | null
  alliance: string | null
}

export interface Battle {
  seq: number
  level: string
  date: string | null
  result: string | null
  coord: { x: number; y: number } | null
  left: Side
  right: Side
  /** Brief battles only. */
  cards: Card[] | null
  identity: { left: Identity; right: Identity } | null
}

export interface Header {
  schema_version: number
  client_version: string
  ocr_model: string
  consent_version: string
  edition: string
  server: string
  session_id: string
  captured_at: string
  anonymous: boolean
}

// ---- primitive checks (throw Invalid with the field path) ----

type Obj = Record<string, unknown>

function record(v: unknown, path: string, allowed: string[]): Obj {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Invalid(`${path}: object expected`)
  const extra = Object.keys(v).find((k) => !allowed.includes(k))
  // The key itself is client text and the reason is stored, so it is not echoed.
  if (extra !== undefined) throw new Invalid(`${path}: unknown key`)
  return v as Obj
}

function required(o: Obj, path: string, keys: string[]): void {
  const missing = keys.find((k) => !Object.hasOwn(o, k))
  if (missing !== undefined) throw new Invalid(`${path}.${missing}: missing`)
}

function int(v: unknown, path: string, min = 0, max = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isSafeInteger(v) || (v as number) < min || (v as number) > max) {
    throw new Invalid(`${path}: integer ${min}..${max} expected`)
  }
  return v as number
}

const intOrNull = (v: unknown, path: string, min?: number, max?: number): number | null =>
  v === null ? null : int(v, path, min, max)

function str(v: unknown, path: string, max = MAX_LABEL): string {
  if (typeof v !== 'string' || v.length === 0 || v.length > max) throw new Invalid(`${path}: string 1..${max} expected`)
  return v
}

function oneOf(v: unknown, path: string, values: string[]): string {
  if (typeof v !== 'string' || !values.includes(v)) throw new Invalid(`${path}: one of ${values.join('/')} expected`)
  return v
}

const oneOfOrNull = (v: unknown, path: string, values: string[]): string | null =>
  v === null ? null : oneOf(v, path, values)

function bool(v: unknown, path: string): boolean {
  if (typeof v !== 'boolean') throw new Invalid(`${path}: boolean expected`)
  return v
}

const boolOrNull = (v: unknown, path: string): boolean | null => (v === null ? null : bool(v, path))

/** A name as the database keys it: NFKC, control / format characters dropped, trimmed; empty is unread. */
export function normName(v: string | null): string | null {
  return v?.normalize('NFKC').replace(INVISIBLE_RE, '').trim() || null
}

/** Length is checked after normalising: NFKC expands some characters (U+FDFA to 18). */
function nameOrNull(v: unknown, path: string, max = MAX_NAME): string | null {
  if (v === undefined || v === null) return null
  if (typeof v !== 'string') throw new Invalid(`${path}: string expected`)
  const name = normName(v)
  if (name !== null && name.length > max) throw new Invalid(`${path}: at most ${max} characters expected`)
  return name
}

/** A hero or skill name: these land in observations (not purged with identities), so letters only. */
function gameName(v: unknown, path: string): string | null {
  if (v === undefined || v === null) return null
  if (typeof v !== 'string') throw new Invalid(`${path}: string expected`)
  const name = normName(v)
  // An unreadable name is dropped rather than losing the whole battle's numbers.
  return name !== null && name.length <= MAX_GAME_NAME && GAME_NAME_RE.test(name) ? name : null
}

/** The game time as the list prints it (`YYYY-MM-DD HH:MM:SS`, cv/listParse.ts readMeta), and a real calendar time. */
function dateOrNull(v: unknown, path: string): string | null {
  if (v === null) return null
  const m = typeof v === 'string' ? DATE_RE.exec(v) : null
  if (!m) throw new Invalid(`${path}: YYYY-MM-DD HH:MM:SS expected`)
  const [Y, M, D, h, min, s] = m.slice(1).map(Number)
  const t = new Date(Date.UTC(Y, M - 1, D, h, min, s))
  const same = t.getUTCFullYear() === Y && t.getUTCMonth() === M - 1 && t.getUTCDate() === D
  if (!same || h > 23 || min > 59 || s > 59) throw new Invalid(`${path}: not a calendar time`)
  return v as string
}

// ---- body ----

/** The body as text, or null when it is over MAX_BODY_BYTES; streamed, so a body without Content-Length stops there too. */
export async function readBody(req: Request, max = MAX_BODY_BYTES): Promise<string | null> {
  const declared = Number(req.headers.get('content-length') ?? '0')
  if (declared > max) return null
  const chunks: Uint8Array[] = []
  let size = 0
  const reader = req.body?.getReader()
  for (let r = await reader?.read(); r && !r.done; r = await reader!.read()) {
    size += r.value.byteLength
    if (size > max) {
      await reader!.cancel()
      return null
    }
    chunks.push(r.value)
  }
  const bytes = new Uint8Array(size)
  let at = 0
  for (const c of chunks) {
    bytes.set(c, at)
    at += c.byteLength
  }
  return new TextDecoder().decode(bytes)
}

// ---- payload ----

/** The upload header; throws Invalid (HTTP 400) for anything malformed. `battles` is checked one by one later. */
export function parseHeader(body: unknown): { header: Header; battles: unknown[] } {
  const o = record(body, 'body', HEADER_KEYS)
  required(o, 'body', HEADER_KEYS)
  if (o.schema_version !== SCHEMA_VERSION) throw new Invalid(`body.schema_version: ${SCHEMA_VERSION} expected`)
  if (typeof o.anonymous !== 'boolean') throw new Invalid('body.anonymous: boolean expected')
  const server = str(o.server, 'body.server', 32)
  if (!SERVER_RE.test(server)) throw new Invalid('body.server: bad format')
  const session = str(o.session_id, 'body.session_id', 36)
  if (!UUID_RE.test(session)) throw new Invalid('body.session_id: uuid expected')
  const captured = str(o.captured_at, 'body.captured_at', 40)
  if (!ISO_RE.test(captured) || Number.isNaN(Date.parse(captured))) throw new Invalid('body.captured_at: ISO-8601 expected')
  if (!Array.isArray(o.battles) || o.battles.length === 0 || o.battles.length > MAX_BATTLES) {
    throw new Invalid(`body.battles: 1..${MAX_BATTLES} battles expected`)
  }
  if (o.consent_version !== CONSENT_VERSION) throw new Invalid(`body.consent_version: ${CONSENT_VERSION} expected`)
  if (o.anonymous && o.battles.some(hasIdentityKeys)) throw new Invalid('body.battles: player/alliance sent in anonymous mode')
  const header: Header = {
    schema_version: SCHEMA_VERSION,
    client_version: str(o.client_version, 'body.client_version'),
    ocr_model: str(o.ocr_model, 'body.ocr_model'),
    consent_version: CONSENT_VERSION,
    edition: oneOf(o.edition, 'body.edition', EDITIONS),
    server,
    session_id: session.toLowerCase(),
    captured_at: captured,
    anonymous: o.anonymous,
  }
  return { header, battles: o.battles }
}

function hasIdentityKeys(b: unknown): boolean {
  if (!b || typeof b !== 'object') return false
  return [(b as Obj).left, (b as Obj).right].some(
    (s) => !!s && typeof s === 'object' && IDENTITY_KEYS.some((k) => Object.hasOwn(s, k)),
  )
}

function parseHero(v: unknown, path: string): Hero {
  const o = record(v, path, HERO_KEYS)
  required(o, path, HERO_KEYS)
  const h: Hero = {
    cfg_id: intOrNull(o.cfg_id, `${path}.cfg_id`, ...CFG_ID),
    name: gameName(o.name, `${path}.name`),
    level: intOrNull(o.level, `${path}.level`, ...HERO_LEVEL),
    red: intOrNull(o.red, `${path}.red`, 0, RED_MAX),
  }
  // The client sends a cfg_id only for a lexicon name.
  if (h.cfg_id !== null && h.name === null) throw new Invalid(`${path}.cfg_id: without a name`)
  return h
}

function parseSide(v: unknown, path: string, anonymous: boolean): { side: Side; identity: Identity } {
  const o = record(v, path, anonymous ? SIDE_KEYS : [...SIDE_KEYS, ...IDENTITY_KEYS])
  required(o, path, SIDE_KEYS)
  if (!Array.isArray(o.heroes) || o.heroes.length !== HEROES_PER_SIDE) {
    throw new Invalid(`${path}.heroes: ${HEROES_PER_SIDE} heroes expected`)
  }
  const side: Side = {
    role: oneOfOrNull(o.role, `${path}.role`, ROLES),
    troop_type: oneOfOrNull(o.troop_type, `${path}.troop_type`, TROOP_TYPES),
    troop_lv: intOrNull(o.troop_lv, `${path}.troop_lv`, ...TROOP_LV),
    hp: intOrNull(o.hp, `${path}.hp`, 0, TROOPS_MAX),
    hp_max: intOrNull(o.hp_max, `${path}.hp_max`, 0, TROOPS_MAX),
    wounded: intOrNull(o.wounded, `${path}.wounded`, 0, TROOPS_MAX),
    dead: intOrNull(o.dead, `${path}.dead`, 0, TROOPS_MAX),
    heroes: o.heroes.map((h, k) => parseHero(h, `${path}.heroes[${k}]`)),
  }
  // Both hold on every real read (hp + wounded + dead <= hp_max too, but a heal could break that, so it is not checked).
  const { hp, hp_max: max, wounded, dead } = side
  if (hp !== null && max !== null && hp > max) throw new Invalid(`${path}.hp: above hp_max`)
  if (wounded !== null && dead !== null && max !== null && wounded + dead > max) {
    throw new Invalid(`${path}: wounded + dead above hp_max`)
  }
  const identity = { player: nameOrNull(o.player, `${path}.player`), alliance: nameOrNull(o.alliance, `${path}.alliance`) }
  return { side, identity }
}

function parseSkill(v: unknown, path: string): Skill {
  const o = record(v, path, SKILL_KEYS)
  required(o, path, SKILL_KEYS)
  return {
    grade: oneOfOrNull(o.grade, `${path}.grade`, GRADES),
    name: gameName(o.name, `${path}.name`),
    launch: intOrNull(o.launch, `${path}.launch`, 0, LAUNCH_MAX),
    kills: intOrNull(o.kills, `${path}.kills`, 0, TROOPS_MAX),
    rescue: intOrNull(o.rescue, `${path}.rescue`, 0, TROOPS_MAX),
  }
}

function parseCard(v: unknown, k: number): Card {
  const path = `cards[${k}]`
  const o = record(v, path, CARD_KEYS)
  required(o, path, CARD_KEYS)
  const team = k < HEROES_PER_SIDE ? 'blue' : 'red'
  const pos = (k % HEROES_PER_SIDE) + 1
  if (o.team !== team) throw new Invalid(`${path}.team: ${team} expected`)
  if (o.pos !== pos) throw new Invalid(`${path}.pos: ${pos} expected`)
  if (!Array.isArray(o.skills) || o.skills.length > MAX_SKILLS) throw new Invalid(`${path}.skills: 0..${MAX_SKILLS} skills expected`)
  return {
    ...parseHero({ cfg_id: o.cfg_id, name: o.name, level: o.level, red: o.red }, path),
    team,
    pos,
    commander: bool(o.commander, `${path}.commander`),
    routed: boolOrNull(o.routed, `${path}.routed`),
    troops: intOrNull(o.troops, `${path}.troops`, 0, TROOPS_MAX),
    skills: o.skills.map((s, i) => parseSkill(s, `${path}.skills[${i}]`)),
  }
}

const sameHero = (h: Hero, c: Card): boolean => HERO_KEYS.every((f) => h[f as keyof Hero] === c[f as keyof Hero])

/** Six cards in screen order; each side's heroes are its three cards' (left = blue). */
function parseCards(v: unknown, left: Side, right: Side): Card[] {
  if (!Array.isArray(v) || v.length !== CARDS) throw new Invalid(`cards: ${CARDS} cards expected`)
  const cards = v.map(parseCard)
  for (const team of [0, 1]) {
    const own = cards.slice(team * HEROES_PER_SIDE, (team + 1) * HEROES_PER_SIDE)
    if (own.filter((c) => c.commander).length > 1) throw new Invalid(`cards: more than one commander on ${own[0].team}`)
    const [name, s] = team === 0 ? ['left', left] : ['right', right]
    const k = own.findIndex((c, i) => !sameHero(s.heroes[i], c))
    if (k >= 0) throw new Invalid(`${name}.heroes[${k}]: differs from cards[${team * HEROES_PER_SIDE + k}]`)
  }
  return cards
}

function parseCoord(v: unknown, path: string): { x: number; y: number } | null {
  if (v === null) return null
  const o = record(v, path, ['x', 'y'])
  required(o, path, ['x', 'y'])
  return { x: int(o.x, `${path}.x`, 0, INT4_MAX), y: int(o.y, `${path}.y`, 0, INT4_MAX) }
}

/** One battle; throws Invalid (the battle is rejected, not the batch). */
export function parseBattle(v: unknown, anonymous: boolean): Battle {
  const o = record(v, 'battle', BRIEF_KEYS)
  const level = oneOf(o.level, 'level', LEVELS)
  const brief = level === 'brief'
  if (!brief && Object.hasOwn(o, 'cards')) throw new Invalid('cards: brief battles only')
  required(o, 'battle', brief ? BRIEF_KEYS : BATTLE_KEYS)
  const left = parseSide(o.left, 'left', anonymous)
  const right = parseSide(o.right, 'right', anonymous)
  return {
    seq: int(o.seq, 'seq', 0, INT4_MAX),
    level,
    date: dateOrNull(o.date, 'date'),
    result: oneOfOrNull(o.result, 'result', RESULTS),
    coord: parseCoord(o.coord, 'coord'),
    left: left.side,
    right: right.side,
    cards: brief ? parseCards(o.cards, left.side, right.side) : null,
    identity: anonymous ? null : { left: left.identity, right: right.identity },
  }
}

// ---- fingerprint ----

const sideKey = (s: Side): (number | null)[] => SIDE_NUMBERS.map((f) => s[f])

function compareKeys(a: number[], b: number[]): number {
  const k = a.findIndex((n, i) => n !== b[i])
  return k < 0 ? 0 : a[k] - b[k]
}

/**
 * date | coord | the two side keys [hp, hp_max, wounded, dead] in canonical (ascending) order, so the opposing
 * alliance's mirrored upload of a battle gets the same fp. `mirrored`: the sort swapped the sides. Null when the
 * date, the coord or any of the eight numbers is unread (a partial key, as in battle-viewer: stored, not deduped).
 */
export function fingerprint(b: Battle): { fp: string | null; mirrored: boolean } {
  const left = sideKey(b.left)
  const right = sideKey(b.right)
  if (b.date === null || b.coord === null || [...left, ...right].some((n) => n === null)) return { fp: null, mirrored: false }
  const mirrored = compareKeys(left as number[], right as number[]) > 0
  const [first, second] = mirrored ? [right, left] : [left, right]
  return { fp: [b.date, `${b.coord.x},${b.coord.y}`, ...first, ...second].join('|'), mirrored }
}

// ---- names ----

export function hmacKey(secret: string): Promise<CryptoKey> {
  const raw = new TextEncoder().encode(secret)
  return crypto.subtle.importKey('raw', raw, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
}

/** Hex HMAC-SHA256 of a normalised name; null for an unread one. */
export async function nameHmac(key: CryptoKey, name: string | null): Promise<string | null> {
  if (name === null) return null
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(name))
  return [...new Uint8Array(mac)].map((x) => x.toString(16).padStart(2, '0')).join('')
}

async function identityRow(key: CryptoKey, id: Identity) {
  return {
    player_hmac: await nameHmac(key, id.player),
    alliance_hmac: await nameHmac(key, id.alliance),
  }
}

// ---- the whole upload ----

export interface Prepared {
  header: Header
  /** What the RPC stores: one entry per accepted battle, no names except their HMACs under `identities`. */
  rows: Record<string, unknown>[]
  rejected: { index: number; reason: string }[]
}

const reason = (e: unknown): string => (e instanceof Invalid ? e.message : 'invalid battle')

/** Validate and shape a parsed body. Throws Invalid for a malformed upload; bad battles go to `rejected`. */
export async function prepare(body: unknown, key: CryptoKey): Promise<Prepared> {
  const { header, battles } = parseHeader(body)
  const rows: Record<string, unknown>[] = []
  const rejected: Prepared['rejected'] = []
  // A brief and its list row share the seq (the client sends the list row's), so the key is (level, seq).
  const seen = new Set<string>()
  for (const [index, raw] of battles.entries()) {
    let b: Battle
    try {
      b = parseBattle(raw, header.anonymous)
    } catch (e) {
      rejected.push({ index, reason: reason(e) })
      continue
    }
    const slot = `${b.level}:${b.seq}`
    if (seen.has(slot)) {
      rejected.push({ index, reason: 'seq: duplicate in payload' })
      continue
    }
    seen.add(slot)
    rows.push(await toRow(b, key))
  }
  return { header, rows, rejected }
}

async function toRow(b: Battle, key: CryptoKey): Promise<Record<string, unknown>> {
  const { identity, cards, ...rest } = b
  const identities = identity && {
    left: await identityRow(key, identity.left),
    right: await identityRow(key, identity.right),
  }
  // A list row carries no `cards` key at all, so the RPC reads SQL NULL for it.
  return { ...rest, ...(cards && { cards }), ...fingerprint(b), identities }
}
