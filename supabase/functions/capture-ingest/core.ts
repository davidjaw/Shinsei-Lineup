// Pure logic of capture-ingest: payload validation, name normalisation, HMAC and the dedup fingerprint.
// No Deno APIs here (Web Crypto only), so node can run the tests: npx tsx --test supabase/functions/capture-ingest/*.test.ts

export const SCHEMA_VERSION = 3
export const MAX_BATTLES = 200
export const MAX_BODY_BYTES = 256 * 1024

// Value sets of the capture client (capture/client/src/prefs.ts, cv/listParse.ts, cv/troopIcon.ts, cv/listPixels.ts).
const EDITIONS = ['tw', 'hk']
const SERVER_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/
const RESULTS = ['win', 'loss', 'draw']
const ROLES = ['attack', 'defend']
const LEVELS = ['list']
const TROOP_TYPES = ['足輕', '弓兵', '騎兵', '鐵炮', '攻城車']
const HERO_LEVEL: [number, number] = [1, 50]
const RED_MAX = 5
const HEROES_PER_SIDE = 3

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/
const MAX_NAME = 64
const MAX_LABEL = 64
/** Postgres int4: seq and coordinates are int columns. */
const INT4_MAX = 2147483647

const HEADER_KEYS = [
  'schema_version', 'client_version', 'ocr_model', 'consent_version', 'edition', 'server',
  'session_id', 'captured_at', 'anonymous', 'battles',
]
const BATTLE_KEYS = ['seq', 'level', 'date', 'result', 'coord', 'left', 'right']
const SIDE_KEYS = ['role', 'troop_type', 'troop_lv', 'hp', 'hp_max', 'wounded', 'dead', 'heroes']
const IDENTITY_KEYS = ['player', 'alliance']
const HERO_KEYS = ['cfg_id', 'name', 'level', 'red']
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
  if (extra !== undefined) throw new Invalid(`${path}.${extra}: unknown key`)
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

/** A name as the database keys it: NFKC and trimmed; empty is unread. */
export function normName(v: string | null): string | null {
  return v?.normalize('NFKC').trim() || null
}

function nameOrNull(v: unknown, path: string): string | null {
  if (v === undefined || v === null) return null
  return normName(str(v, path, MAX_NAME))
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
  if (o.anonymous && o.battles.some(hasIdentityKeys)) throw new Invalid('body.battles: player/alliance sent in anonymous mode')
  const header: Header = {
    schema_version: SCHEMA_VERSION,
    client_version: str(o.client_version, 'body.client_version'),
    ocr_model: str(o.ocr_model, 'body.ocr_model'),
    consent_version: str(o.consent_version, 'body.consent_version'),
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
  return {
    cfg_id: intOrNull(o.cfg_id, `${path}.cfg_id`),
    name: nameOrNull(o.name, `${path}.name`),
    level: intOrNull(o.level, `${path}.level`, ...HERO_LEVEL),
    red: intOrNull(o.red, `${path}.red`, 0, RED_MAX),
  }
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
    troop_lv: intOrNull(o.troop_lv, `${path}.troop_lv`),
    hp: intOrNull(o.hp, `${path}.hp`),
    hp_max: intOrNull(o.hp_max, `${path}.hp_max`),
    wounded: intOrNull(o.wounded, `${path}.wounded`),
    dead: intOrNull(o.dead, `${path}.dead`),
    heroes: o.heroes.map((h, k) => parseHero(h, `${path}.heroes[${k}]`)),
  }
  if (side.hp !== null && side.hp_max !== null && side.hp > side.hp_max) throw new Invalid(`${path}.hp: above hp_max`)
  const identity = { player: nameOrNull(o.player, `${path}.player`), alliance: nameOrNull(o.alliance, `${path}.alliance`) }
  return { side, identity }
}

function parseCoord(v: unknown, path: string): { x: number; y: number } | null {
  if (v === null) return null
  const o = record(v, path, ['x', 'y'])
  required(o, path, ['x', 'y'])
  return { x: int(o.x, `${path}.x`, 0, INT4_MAX), y: int(o.y, `${path}.y`, 0, INT4_MAX) }
}

/** One battle; throws Invalid (the battle is rejected, not the batch). */
export function parseBattle(v: unknown, anonymous: boolean): Battle {
  const o = record(v, 'battle', BATTLE_KEYS)
  required(o, 'battle', BATTLE_KEYS)
  const left = parseSide(o.left, 'left', anonymous)
  const right = parseSide(o.right, 'right', anonymous)
  return {
    seq: int(o.seq, 'seq', 0, INT4_MAX),
    level: oneOf(o.level, 'level', LEVELS),
    date: dateOrNull(o.date, 'date'),
    result: oneOfOrNull(o.result, 'result', RESULTS),
    coord: parseCoord(o.coord, 'coord'),
    left: left.side,
    right: right.side,
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
    player_raw: id.player,
    alliance_raw: id.alliance,
    player_hmac: await nameHmac(key, id.player),
    alliance_hmac: await nameHmac(key, id.alliance),
  }
}

// ---- the whole upload ----

export interface Prepared {
  header: Header
  /** What the RPC stores: one entry per accepted battle, no names except under `identities`. */
  rows: Record<string, unknown>[]
  rejected: { index: number; reason: string }[]
}

const reason = (e: unknown): string => (e instanceof Invalid ? e.message : 'invalid battle')

/** Validate and shape a parsed body. Throws Invalid for a malformed upload; bad battles go to `rejected`. */
export async function prepare(body: unknown, key: CryptoKey): Promise<Prepared> {
  const { header, battles } = parseHeader(body)
  const rows: Record<string, unknown>[] = []
  const rejected: Prepared['rejected'] = []
  const seen = new Set<number>()
  for (const [index, raw] of battles.entries()) {
    let b: Battle
    try {
      b = parseBattle(raw, header.anonymous)
    } catch (e) {
      rejected.push({ index, reason: reason(e) })
      continue
    }
    if (seen.has(b.seq)) {
      rejected.push({ index, reason: 'seq: duplicate in payload' })
      continue
    }
    seen.add(b.seq)
    rows.push(await toRow(b, key))
  }
  return { header, rows, rejected }
}

async function toRow(b: Battle, key: CryptoKey): Promise<Record<string, unknown>> {
  const { identity, ...rest } = b
  const identities = identity && {
    left: await identityRow(key, identity.left),
    right: await identityRow(key, identity.right),
  }
  return { ...rest, ...fingerprint(b), identities }
}
