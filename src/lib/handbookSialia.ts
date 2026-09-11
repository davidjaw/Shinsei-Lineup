// Official Sialia handbook share snapshot (player inventory).
// Used by the Vite dev proxy and the mapping layer. The browser never
// calls this host directly — prod goes through the Supabase edge function.

export const SIALIA_SNAPSHOT_URL =
  'https://p11386-platform.sialiagamesinc.com.tw/sns/web/api/cache/get_player_share_snapshot'

export const SIALIA_GAME_ID = 's11'

export const SNAPSHOT_ID_RE = /^[0-9a-f]{16,}$/i

export interface HandbookSnapshot {
  player_id: string | null
  hero_ids: number[]
  skill_ids: number[]
  hero_count: number
  skill_count: number
}

const SELECTORS = [
  { selector_type: 'view', data_view_type: 'asset_overview' },
  { selector_type: 'view', data_view_type: 'hero' },
  { selector_type: 'view', data_view_type: 'skill' },
] as const

export function parseSnapshotId(source: string): string | null {
  const trimmed = source.trim()
  if (!trimmed) return null
  if (SNAPSHOT_ID_RE.test(trimmed)) return trimmed
  const embedded = trimmed.match(/snapshot_id=([0-9a-f]{16,})/i)
  if (embedded) return embedded[1]

  let fragment = ''
  let query = ''
  try {
    const parsed = new URL(trimmed)
    fragment = parsed.hash.replace(/^#/, '')
    query = parsed.search.replace(/^\?/, '')
  } catch {
    const hashIdx = trimmed.indexOf('#')
    if (hashIdx >= 0) fragment = trimmed.slice(hashIdx + 1)
    const qIdx = trimmed.indexOf('?')
    if (qIdx >= 0 && hashIdx < 0) query = trimmed.slice(qIdx + 1)
  }

  const blobs = [
    fragment.includes('?') ? fragment.slice(fragment.indexOf('?') + 1) : fragment,
    query,
  ]
  for (const blob of blobs) {
    if (!blob) continue
    const params = new URLSearchParams(blob)
    const id = params.get('snapshot_id')
    if (id && SNAPSHOT_ID_RE.test(id)) return id
  }
  return null
}

const asInt = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value !== '') {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

interface SnapshotBlock {
  selector?: { data_view_type?: string }
  player_id?: string
  player_data?: {
    heros?: Array<{ id?: unknown; type?: unknown }>
    skills?: Array<{ id?: unknown; type?: unknown }>
    hero_count?: unknown
    skill_count?: unknown
  }
}

const idsFrom = (rows: Array<{ id?: unknown; type?: unknown }> | undefined): number[] => {
  const out: number[] = []
  for (const row of rows ?? []) {
    const id = asInt(row.type ?? row.id)
    if (id != null) out.push(id)
  }
  return out
}

export async function fetchSialiaSnapshot(
  snapshotId: string,
  init?: { timeoutMs?: number },
): Promise<HandbookSnapshot> {
  if (!SNAPSHOT_ID_RE.test(snapshotId)) {
    throw new Error('無效的 snapshot_id')
  }
  const payload = {
    game_id: SIALIA_GAME_ID,
    selectors: SELECTORS,
    snapshot_id: snapshotId,
  }
  const url = `${SIALIA_SNAPSHOT_URL}?_json=${encodeURIComponent(JSON.stringify(payload))}`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), init?.timeoutMs ?? 15_000)
  let res: Response
  try {
    res = await fetch(url, {
      method: 'GET',
      headers: {
        accept: 'application/json',
        origin: 'https://general.sialiagamesinc.com.tw',
        referer: 'https://general.sialiagamesinc.com.tw/xzdyw-station-sialiagamesinc',
      },
      signal: ctrl.signal,
    })
  } catch (e) {
    const aborted = e instanceof Error && e.name === 'AbortError'
    throw new Error(aborted ? '官方圖鑑回應逾時' : '無法連線官方圖鑑')
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) throw new Error(`官方圖鑑回應 ${res.status}`)
  const body = (await res.json()) as { code?: number; message?: string; data?: SnapshotBlock[] }
  if (body.code !== 0) {
    throw new Error(body.message ? `官方圖鑑：${body.message}` : '找不到此分享快照')
  }
  const blocks = new Map<string, SnapshotBlock>()
  for (const block of body.data ?? []) {
    const view = block.selector?.data_view_type
    if (view) blocks.set(view, block)
  }
  const overview = blocks.get('asset_overview')
  const heroBlock = blocks.get('hero')
  const skillBlock = blocks.get('skill')
  const heroIds = idsFrom(heroBlock?.player_data?.heros)
  const skillIds = idsFrom(skillBlock?.player_data?.skills)
  const playerId =
    heroBlock?.player_id ?? skillBlock?.player_id ?? overview?.player_id ?? null
  return {
    player_id: playerId != null ? String(playerId) : null,
    hero_ids: heroIds,
    skill_ids: skillIds,
    hero_count: asInt(overview?.player_data?.hero_count) ?? heroIds.length,
    skill_count: asInt(overview?.player_data?.skill_count) ?? skillIds.length,
  }
}
