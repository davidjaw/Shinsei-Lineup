// Capture the raw URL hash at module-load time, BEFORE vue-router has a chance
// to normalize it. createWebHashHistory prepends a `/` to any hash that doesn't
// already start with one (e.g. `#s/abc` → `#/s/abc`, `#access_token=foo` →
// `#/access_token=foo`), which breaks our share/auth callback parsers:
//   - URLSearchParams reads `/access_token` as the first key (not `access_token`)
//   - `hash.startsWith('s/')` returns false for `/s/abc`
//   - base64 decoders choke on the leading slash
//
// Parsers must still tolerate the rewritten form: refresh / copy-paste of the
// address bar captures `#/s/…` or `#/access_token=…` because the snapshot runs
// after a previous visit already rewrote the live hash.
//
// This module MUST be imported before src/router/index.ts so the capture runs
// before the router constructor calls history.replaceState.

const captured: string = typeof window !== 'undefined' ? window.location.hash : ''
let consumed = false

/**
 * Strip a leading `#` then a single optional leading `/` (vue-router rewrite).
 * Use this wherever a parser consumes a hash blob.
 */
export function normalizeHash(hash: string): string {
  let payload = hash.startsWith('#') ? hash.slice(1) : hash
  if (payload.startsWith('/')) payload = payload.slice(1)
  return payload
}

/**
 * True if the hash looks like a share slug, OAuth callback, or legacy base64
 * blob (no extra `/` in the body). Used by the catch-all guard so typed
 * garbage (`#/foo/bar`) redirects to `/` while `#s/…`, `#/s/…`, auth, and
 * `#<base64>` still reach LineupBuilder.
 */
export function isShareOrAuthHash(hash: string): boolean {
  const payload = normalizeHash(hash)
  if (!payload) return false
  if (payload.startsWith('s/')) return true
  if (payload.includes('access_token=') || payload.includes('error=')) return true
  return !payload.includes('/')
}

/**
 * Returns the URL hash (including leading `#`) that the user landed on, before
 * vue-router had a chance to normalize it. Returns '' on subsequent calls so
 * a hash is consumed exactly once per page load.
 */
export function consumeInitialHash(): string {
  if (consumed) return ''
  consumed = true
  return captured
}

/**
 * Non-destructive read of the initial hash. Use from router guards that need
 * to discriminate between share-blob URLs and ordinary user paths BEFORE the
 * route mounts and consumes the hash. Returns '' if already consumed.
 */
export function peekInitialHash(): string {
  return consumed ? '' : captured
}
