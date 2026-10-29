// Operator tool for data-removal requests on the capture database. It only PRINTS SQL (paste it into the
// project's SQL Editor, dev or prod as intended); nothing here connects to a database.
//
//   CAPTURE_NAME_HMAC_KEY=… npx tsx script/capture_requests.ts lookup      --name <player> [--alliance] [--server S00001]
//   CAPTURE_NAME_HMAC_KEY=… npx tsx script/capture_requests.ts remove-name --name <player> [--alliance] [--server S00001]
//                           npx tsx script/capture_requests.ts remove-user --user-id <uuid>
//
// The name is normalised and HMAC'd exactly as capture-ingest does, so a name matches only when it is spelled the
// way the game prints it. `remove-name` clears the HMAC (the battle numbers stay: a battle row holds no names);
// `--alliance` targets the alliance name instead of the player name. `remove-user` deletes the user's uploads and
// everything below them, then prunes battles nobody points at; deleting the auth account itself stays in the
// dashboard (the account is shared with the lineup site).

import { hmacKey, nameHmac, normName } from '../supabase/functions/capture-ingest/core.ts'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SERVER_RE = /^(PK|S)\d{5}$/

function flags(args: string[]): Map<string, string | true> {
  const out = new Map<string, string | true>()
  for (let i = 0; i < args.length; i++) {
    if (!args[i].startsWith('--')) throw new Error(`unexpected argument ${args[i]}`)
    const key = args[i].slice(2)
    const next = args[i + 1]
    if (next === undefined || next.startsWith('--')) out.set(key, true)
    else (out.set(key, next), i++)
  }
  return out
}

function text(f: Map<string, string | true>, key: string): string | undefined {
  const v = f.get(key)
  if (v === true) throw new Error(`--${key} needs a value`)
  return v
}

/** SQL literal of a string; the inputs here are validated, quotes are doubled anyway. */
const lit = (s: string): string => `'${s.replaceAll("'", "''")}'`

async function nameFilter(f: Map<string, string | true>): Promise<{ column: string; where: string; hex: string }> {
  const secret = process.env.CAPTURE_NAME_HMAC_KEY ?? ''
  if (!secret) throw new Error('CAPTURE_NAME_HMAC_KEY is not set')
  const name = normName(text(f, 'name') ?? null)
  if (!name) throw new Error('--name is required')
  const hex = (await nameHmac(await hmacKey(secret), name)) as string
  const column = f.get('alliance') === true ? 'alliance_hmac' : 'player_hmac'
  const server = text(f, 'server')
  if (server !== undefined && !SERVER_RE.test(server)) throw new Error('--server: PK or S and five digits expected')
  const scope = server ? ` AND o.server = ${lit(server)}` : ''
  return {
    column,
    hex,
    where: `i.${column} = decode(${lit(hex)}, 'hex')${scope}`,
  }
}

export async function build(cmd: string, f: Map<string, string | true>): Promise<string> {
  if (cmd === 'lookup') {
    const { where } = await nameFilter(f)
    return `SELECT o.edition, o.server, count(*) AS rows, count(DISTINCT o.user_id) AS uploaders,
       min(o.battle_at) AS first_battle, max(o.battle_at) AS last_battle
  FROM capture.identities i JOIN capture.observations o ON o.id = i.observation_id
 WHERE ${where}
 GROUP BY o.edition, o.server ORDER BY o.edition, o.server;`
  }
  if (cmd === 'remove-name') {
    const { column, where } = await nameFilter(f)
    return `BEGIN;
UPDATE capture.identities i SET ${column} = NULL
  FROM capture.observations o
 WHERE o.id = i.observation_id AND ${where};
DELETE FROM capture.identities WHERE player_hmac IS NULL AND alliance_hmac IS NULL;
COMMIT;`
  }
  if (cmd === 'remove-user') {
    const id = text(f, 'user-id')
    if (!id || !UUID_RE.test(id)) throw new Error('--user-id: a uuid is required')
    return `BEGIN;
DELETE FROM capture.uploads WHERE user_id = ${lit(id)};
SELECT capture.prune_battles() AS battles_pruned;
COMMIT;`
  }
  throw new Error('usage: lookup | remove-name | remove-user (see the header of this file)')
}

if (process.argv[1]?.endsWith('capture_requests.ts')) {
  const [cmd = '', ...rest] = process.argv.slice(2)
  build(cmd, flags(rest)).then(
    (sql) => console.log(sql),
    (e: Error) => {
      console.error(e.message)
      process.exit(1)
    },
  )
}
