// Public proxy for Sialia handbook share snapshots.
// Browser cannot call p11386-platform (no CORS + prod CSP connect-src).
// Returns ids only — no talent / attrs / equipped slots.
// Deploy with verify_jwt = false (config.toml / --no-verify-jwt): gateway
// JWT would 401 OPTIONS preflight and GitHub Pages would report CORS.

const SIALIA_SNAPSHOT_URL =
  'https://p11386-platform.sialiagamesinc.com.tw/sns/web/api/cache/get_player_share_snapshot'
const SIALIA_GAME_ID = 's11'
const SNAPSHOT_ID_RE = /^[0-9a-f]{16,}$/i

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...cors, 'Content-Type': 'application/json' },
  })

const asInt = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value !== '') {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  if (req.method !== 'POST') return json({ error: 'method not allowed' }, 405)

  let snapshotId = ''
  try {
    const body = (await req.json()) as { snapshot_id?: unknown }
    snapshotId = typeof body.snapshot_id === 'string' ? body.snapshot_id.trim() : ''
  } catch {
    return json({ error: 'invalid json' }, 400)
  }
  if (!SNAPSHOT_ID_RE.test(snapshotId)) {
    return json({ error: '無效的 snapshot_id' }, 400)
  }

  const payload = {
    game_id: SIALIA_GAME_ID,
    snapshot_id: snapshotId,
    selectors: [
      { selector_type: 'view', data_view_type: 'asset_overview' },
      { selector_type: 'view', data_view_type: 'hero' },
      { selector_type: 'view', data_view_type: 'skill' },
    ],
  }
  const url = `${SIALIA_SNAPSHOT_URL}?_json=${encodeURIComponent(JSON.stringify(payload))}`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 15_000)
  let upstream: Response
  try {
    upstream = await fetch(url, {
      headers: {
        accept: 'application/json',
        origin: 'https://general.sialiagamesinc.com.tw',
        referer: 'https://general.sialiagamesinc.com.tw/xzdyw-station-sialiagamesinc',
      },
      signal: ctrl.signal,
    })
  } catch (e) {
    const aborted = e instanceof Error && e.name === 'AbortError'
    return json({ error: aborted ? '官方圖鑑回應逾時' : '無法連線官方圖鑑' }, 502)
  } finally {
    clearTimeout(timer)
  }
  if (!upstream.ok) return json({ error: `官方圖鑑回應 ${upstream.status}` }, 502)

  const raw = await upstream.json() as {
    code?: number
    message?: string
    data?: Array<{
      selector?: { data_view_type?: string }
      player_id?: string
      player_data?: {
        heros?: Array<{ id?: unknown; type?: unknown }>
        skills?: Array<{ id?: unknown; type?: unknown }>
        hero_count?: unknown
        skill_count?: unknown
      }
    }>
  }
  if (raw.code !== 0) {
    return json({ error: raw.message ? `官方圖鑑：${raw.message}` : '找不到此分享快照' }, 404)
  }

  const blocks = new Map<string, NonNullable<typeof raw.data>[number]>()
  for (const block of raw.data ?? []) {
    const view = block.selector?.data_view_type
    if (view) blocks.set(view, block)
  }
  const idsFrom = (rows: Array<{ id?: unknown; type?: unknown }> | undefined): number[] => {
    const out: number[] = []
    for (const row of rows ?? []) {
      const id = asInt(row.type ?? row.id)
      if (id != null) out.push(id)
    }
    return out
  }
  const overview = blocks.get('asset_overview')
  const heroBlock = blocks.get('hero')
  const skillBlock = blocks.get('skill')
  const hero_ids = idsFrom(heroBlock?.player_data?.heros)
  const skill_ids = idsFrom(skillBlock?.player_data?.skills)
  const player_id = heroBlock?.player_id ?? skillBlock?.player_id ?? overview?.player_id ?? null

  return json({
    player_id: player_id != null ? String(player_id) : null,
    hero_ids,
    skill_ids,
    hero_count: asInt(overview?.player_data?.hero_count) ?? hero_ids.length,
    skill_count: asInt(overview?.player_data?.skill_count) ?? skill_ids.length,
  })
})
