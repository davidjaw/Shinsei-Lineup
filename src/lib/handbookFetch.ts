import { SUPABASE_KEY, SUPABASE_URL, fetchWithTimeout, isSupabaseConfigured } from './supabase'
import type { HandbookSnapshot } from './handbookSialia'

export type { HandbookSnapshot }

// Sialia aborts at 15s; leave slack for the proxy/edge hop and cold start.
const HANDBOOK_FETCH_TIMEOUT_MS = 20_000

const readError = async (res: Response): Promise<string> => {
  try {
    const body = (await res.json()) as { error?: string; message?: string }
    return body.error || body.message || `匯入服務回應 ${res.status}`
  } catch {
    return `匯入服務回應 ${res.status}`
  }
}

const postSnapshot = async (url: string, headers: HeadersInit, body: string): Promise<HandbookSnapshot> => {
  let res: Response
  try {
    res = await fetchWithTimeout(url, { method: 'POST', headers, body }, HANDBOOK_FETCH_TIMEOUT_MS)
  } catch (e) {
    const aborted = e instanceof Error && e.name === 'AbortError'
    throw new Error(aborted ? '官方圖鑑回應逾時' : '無法連線官方圖鑑')
  }
  if (!res.ok) throw new Error(await readError(res))
  return (await res.json()) as HandbookSnapshot
}

export async function fetchHandbookSnapshot(snapshotId: string): Promise<HandbookSnapshot> {
  const payload = JSON.stringify({ snapshot_id: snapshotId })

  if (import.meta.env.DEV) {
    return postSnapshot('/api/handbook-snapshot', { 'Content-Type': 'application/json' }, payload)
  }

  if (!isSupabaseConfigured()) {
    throw new Error('匯入服務未配置（需要 Supabase edge function）')
  }
  return postSnapshot(
    `${SUPABASE_URL}/functions/v1/handbook-snapshot`,
    {
      'Content-Type': 'application/json',
      apikey: SUPABASE_KEY!,
      Authorization: `Bearer ${SUPABASE_KEY}`,
    },
    payload,
  )
}
