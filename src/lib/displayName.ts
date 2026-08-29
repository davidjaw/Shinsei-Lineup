// Display helpers for public author tags and variant team titles.
// Hide/report logic lives on the server; this file only formats what the
// client already received.

export const AUTHOR_NAME_MAX = 30
export const TEAM_NAME_MAX = 50

/** Last 4 hex chars of a uuid (dashes stripped). Null if missing/short. */
export function userHex(userId: string | null | undefined): string | null {
  if (!userId) return null
  const hex = userId.replace(/-/g, '').toLowerCase()
  if (hex.length < 4) return null
  return hex.slice(-4)
}

export function formatUserTag(name: string, userId: string | null | undefined): string {
  const hex = userHex(userId)
  return hex ? `${name}#${hex}` : name
}

export function capAuthorName(name: string | null | undefined): string | null {
  const s = (name ?? '').trim().slice(0, AUTHOR_NAME_MAX)
  return s === '' ? null : s
}

export function capTeamName(name: string | null | undefined): string | null {
  const s = (name ?? '').trim().slice(0, TEAM_NAME_MAX)
  return s === '' ? null : s
}

export function resolveAuthorLabel(c: {
  userId: string
  authorName: string | null
  authorNameHidden: boolean
  authorNameLocked?: boolean
} | null | undefined): string {
  if (!c) return '匿名'
  if (c.authorNameLocked || c.authorNameHidden) return formatUserTag('用戶', c.userId)
  return formatUserTag(c.authorName?.trim() || '匿名', c.userId)
}

/** Structured author for <UserTag>. Hidden names still carry the raw string
 *  so a spoiler can reveal them; locked names never expose the raw string. */
export function resolveAuthorParts(
  c: {
    userId: string
    authorName: string | null
    authorNameHidden: boolean
    authorNameLocked?: boolean
  } | null | undefined,
  fallbackUserId?: string | null,
): { name: string; userId: string | null; hidden: boolean; locked: boolean } {
  if (!c) return { name: '匿名', userId: fallbackUserId ?? null, hidden: false, locked: false }
  if (c.authorNameLocked) {
    return { name: '已隱藏', userId: c.userId, hidden: true, locked: true }
  }
  return {
    name: c.authorName?.trim() || '匿名',
    userId: c.userId,
    hidden: c.authorNameHidden,
    locked: false,
  }
}

export function resolvePublicTeamTitle(
  firstAuthorId: string | null,
  contributors: Array<{
    userId: string
    teamName: string | null
    teamNameHidden: boolean
    teamNameLocked?: boolean
    contributedAt: string
  }>,
): { text: string | null; sourceUserId: string | null; hidden: boolean; locked: boolean } {
  // First-author first, then others in their original relative order.
  const first: typeof contributors = []
  const others: typeof contributors = []
  for (const c of contributors) {
    if (firstAuthorId && c.userId === firstAuthorId) first.push(c)
    else others.push(c)
  }
  const ordered = first.concat(others)
  // A locked row is still "named" even when GET nulled team_name — do not
  // skip it and leak a later contributor's title.
  const named = ordered.filter(c =>
    c.teamNameLocked || (c.teamName?.trim() ?? '') !== '',
  )
  const picked = named[0]
  if (!picked) return { text: null, sourceUserId: null, hidden: false, locked: false }
  if (picked.teamNameLocked) {
    return {
      text: '••••',
      sourceUserId: picked.userId,
      hidden: true,
      locked: true,
    }
  }
  return {
    text: picked.teamName!.trim(),
    sourceUserId: picked.userId,
    hidden: picked.teamNameHidden,
    locked: false,
  }
}
