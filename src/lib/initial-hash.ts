// Capture the raw URL hash at module-load time, BEFORE vue-router has a chance
// to normalize it. createWebHashHistory prepends a `/` to any hash that doesn't
// already start with one (e.g. `#s/abc` → `#/s/abc`, `#access_token=foo` →
// `#/access_token=foo`), which breaks our share/auth callback parsers:
//   - URLSearchParams reads `/access_token` as the first key (not `access_token`)
//   - `hash.startsWith('s/')` returns false for `/s/abc`
//   - base64 decoders choke on the leading slash
//
// This module MUST be imported before src/router/index.ts so the capture runs
// before the router constructor calls history.replaceState.

const captured: string = typeof window !== 'undefined' ? window.location.hash : ''
let consumed = false

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
