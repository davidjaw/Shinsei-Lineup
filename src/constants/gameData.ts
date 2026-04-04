import { Trait } from '../composables/useData'

export const MOCK_EQUIP_TRAITS: Trait[] = [
  { name: '武力+5', rank: 'B', active: true, description: '武力提升5點' },
  { name: '統率+5', rank: 'B', active: true, description: '統率提升5點' },
  { name: '智略+5', rank: 'B', active: true, description: '智略提升5點' },
  { name: '速度+5', rank: 'B', active: true, description: '速度提升5點' },
  { name: '攻城', rank: 'A', active: true, description: '對城池傷害提升' },
  { name: '馬術', rank: 'C', active: true, description: '騎兵適性提升' }
]

export interface ShareableLineup {
  name?: string
  m?: string; m_s1?: string; m_s2?: string; m_st?: any; m_eq?: any[]
  v1?: string; v1_s1?: string; v1_s2?: string; v1_st?: any; v1_eq?: any[]
  v2?: string; v2_s1?: string; v2_s2?: string; v2_st?: any; v2_eq?: any[]
}

export interface ShareableData {
  inv_h?: string[]
  inv_s?: string[]
  inventory?: string[] // legacy support
  lineups?: ShareableLineup[]
}