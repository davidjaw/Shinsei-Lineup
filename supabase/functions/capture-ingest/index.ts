// Battle-report uploads from the capture web client (contract: schema_version 3).
// Verifies the user with GoTrue, validates the payload (core.ts), then writes through the
// service-role-only RPC public.capture_ingest, which also enforces bans, rate limits and dedup.
// Deploy with verify_jwt = false (config.toml / --no-verify-jwt): gateway JWT would 401 the OPTIONS
// preflight. The user is verified here instead.
//
// Env: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY (provided by the platform),
//      CAPTURE_ALLOWED_ORIGINS (comma-separated exact origins), CAPTURE_NAME_HMAC_KEY (secret).

import { hmacKey, Invalid, MAX_BODY_BYTES, prepare } from './core.ts'

const SUPABASE_URL = Deno.env.get('SUPABASE_URL') ?? ''
const ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY') ?? ''
const SERVICE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
const HMAC_SECRET = Deno.env.get('CAPTURE_NAME_HMAC_KEY') ?? ''
const ALLOWED_ORIGINS = new Set(
  (Deno.env.get('CAPTURE_ALLOWED_ORIGINS') ?? '').split(',').map((o) => o.trim()).filter(Boolean),
)

const corsFor = (origin: string) => ({
  'Access-Control-Allow-Origin': origin,
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  Vary: 'Origin',
})

const json = (origin: string, body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...corsFor(origin), 'Content-Type': 'application/json' },
  })

/** The caller's user id, or null when the bearer token is missing, not a live session, or an anonymous sign-in. */
async function userId(req: Request): Promise<string | null> {
  const auth = req.headers.get('authorization') ?? ''
  if (!/^Bearer \S+$/.test(auth)) return null
  const res = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: { Authorization: auth, apikey: ANON_KEY },
  })
  if (!res.ok) return null
  const user = (await res.json()) as { id?: unknown; is_anonymous?: unknown }
  return typeof user.id === 'string' && user.is_anonymous !== true ? user.id : null
}

/** The body as text, or null when it is over MAX_BODY_BYTES. */
async function readBody(req: Request): Promise<string | null> {
  const declared = Number(req.headers.get('content-length') ?? '0')
  if (declared > MAX_BODY_BYTES) return null
  const bytes = new Uint8Array(await req.arrayBuffer())
  return bytes.byteLength > MAX_BODY_BYTES ? null : new TextDecoder().decode(bytes)
}

// A legacy service_role key is a JWT and also goes as the bearer; an sb_secret_ key is not a JWT, so it goes as
// `apikey` only (the gateway maps it to service_role).
const SERVICE_HEADERS: Record<string, string> = SERVICE_KEY.startsWith('eyJ')
  ? { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` }
  : { apikey: SERVICE_KEY }

async function rpc(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/rpc/capture_ingest`, {
    method: 'POST',
    headers: { ...SERVICE_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(args),
  })
  if (!res.ok) throw new Error(`capture_ingest ${res.status}: ${await res.text()}`)
  return (await res.json()) as Record<string, unknown>
}

const RPC_ERRORS: Record<string, [string, number]> = {
  banned: ['account banned', 403],
  rate_limited: ['rate limit exceeded', 429],
}

async function handle(req: Request, origin: string): Promise<Response> {
  const user = await userId(req)
  if (!user) return json(origin, { error: 'login required' }, 401)

  const text = await readBody(req)
  if (text === null) return json(origin, { error: 'body too large' }, 413)

  let prepared
  try {
    prepared = await prepare(JSON.parse(text), await hmacKey(HMAC_SECRET))
  } catch (e) {
    if (e instanceof SyntaxError) return json(origin, { error: 'invalid json' }, 400)
    if (e instanceof Invalid) return json(origin, { error: e.message }, 400)
    throw e
  }

  const { header, rows, rejected } = prepared
  const out = await rpc({ p_user_id: user, p_header: header, p_battles: rows, p_rejected: rejected })
  const failure = RPC_ERRORS[String(out.error ?? '')]
  if (failure) return json(origin, { error: failure[0] }, failure[1])
  return json(origin, { accepted: out.accepted, duplicates: out.duplicates, rejected })
}

Deno.serve(async (req) => {
  const origin = req.headers.get('origin') ?? ''
  // No CORS headers here: a page of another origin is not a client, so it must not read even the error.
  if (!ALLOWED_ORIGINS.has(origin)) return new Response('origin not allowed', { status: 403 })
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsFor(origin) })
  if (req.method !== 'POST') return json(origin, { error: 'method not allowed' }, 405)
  if (!SUPABASE_URL || !ANON_KEY || !SERVICE_KEY || !HMAC_SECRET) return json(origin, { error: 'not configured' }, 500)
  try {
    return await handle(req, origin)
  } catch (e) {
    console.error(e)
    return json(origin, { error: 'internal error' }, 500)
  }
})
