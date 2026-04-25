import { Trait } from '../composables/useData'

export const TRANSPARENT_GIF = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

const RATE_RANGE_REGEX = /(\d+(?:\.\d+)?%?)\s*(?:->|to|→)\s*(\d+(?:\.\d+)?%?)/
export const formatRate = (rateStr: string | undefined, maxLevel: boolean): string => {
  if (!rateStr) return ''
  const match = rateStr.match(RATE_RANGE_REGEX)
  if (match) return maxLevel ? match[2] : match[1]
  return rateStr
}

export const getTraitColor = (rank: string): string => {
  // Balanced palette: same shade weight (50/300/700) across all tiers.
  switch (rank) {
    case 'S': return 'bg-yellow-50 border-yellow-300 text-yellow-700 font-bold'
    case 'A': return 'bg-purple-50 border-purple-300 text-purple-700 font-bold'
    case 'B': return 'bg-blue-50 border-blue-300 text-blue-700 font-bold'
    case 'C': return 'bg-green-50 border-green-300 text-green-700 font-bold'
    default:  return 'bg-gray-50 border-gray-200 text-gray-500'
  }
}

export const MOCK_EQUIP_TRAITS: Trait[] = [
  { name: '武力+5', rank: 'B', active: true, description: '武力提升5點' },
  { name: '統率+5', rank: 'B', active: true, description: '統率提升5點' },
  { name: '智略+5', rank: 'B', active: true, description: '智略提升5點' },
  { name: '速度+5', rank: 'B', active: true, description: '速度提升5點' },
  { name: '攻城', rank: 'A', active: true, description: '對城池傷害提升' },
  { name: '馬術', rank: 'C', active: true, description: '騎兵適性提升' }
]

// Compact bingxue payload — `d` = CHT direction, `m` = major JP name,
// `n` = array of { n: minor JP name, l: level 1|2 }.
export interface ShareableBingxue {
  d: string | null
  m: string | null
  n: { n: string; l: number }[]
}

export interface ShareableLineup {
  name?: string
  m?: string; m_s1?: string; m_s2?: string; m_st?: any; m_eq?: any[]; m_bt?: number; m_bx?: ShareableBingxue
  v1?: string; v1_s1?: string; v1_s2?: string; v1_st?: any; v1_eq?: any[]; v1_bt?: number; v1_bx?: ShareableBingxue
  v2?: string; v2_s1?: string; v2_s2?: string; v2_st?: any; v2_eq?: any[]; v2_bt?: number; v2_bx?: ShareableBingxue
}

export interface ShareableData {
  v?: number  // format version. Absent = v1 (CHT names). 2 = JP names (rename-resilient).
  inv_h?: string[]
  inv_s?: string[]
  inventory?: string[] // legacy support
  lineups?: ShareableLineup[]
}