import { ref } from 'vue'

export interface SkillVar {
  base: number;
  max: number;
  scale?: string;
}

export interface Skill {
  id: string;
  name: string;
  // null for override-added skills not yet on game8.jp — distinguishes "no JP
  // key" from "JP key not loaded yet" so the CHT⇄JP fallback can fire correctly
  name_jp?: string | null;
  // Historical names this skill replaced (e.g. fixed typos). Profile/inventory
  // lookups treat these as alternate keys so saved references still resolve.
  aliases?: string[];
  // Official cfg.json numeric id (Sialia). Missing on override-only entries.
  cfg_id?: number;

  type: string;
  tags: string[];
  rarity: string;
  icon: string;
  description: string;
  commander_description?: string;
  activation_rate?: string;
  target?: string;
  vars?: Record<string, SkillVar | number>;
  source_hero?: string;
  unique_hero?: string;
  is_unique?: boolean;
  is_teachable?: boolean;
  is_fixed?: boolean;
  is_event_skill?: boolean;
  brief_description?: string;
  related_stats?: string[];
}

export interface TroopAffinity {
  troop_types: string[]
  level: number
  level_cap_bonus: number
}

export interface Trait {
  name: string
  rank: 'S' | 'A' | 'B' | 'C'
  active: boolean
  description?: string
  vars?: Record<string, any>
  affinity?: TroopAffinity | null
}

export type BingxueDirection = '武略' | '陣立' | '機略' | '臨戰'
export const BINGXUE_DIRECTIONS: BingxueDirection[] = ['武略', '陣立', '機略', '臨戰']
export type BingxueTier = 'major' | 'minor'

export interface BingxueOption {
  name: string           // CHT display name
  name_jp: string        // JP key — used in references
  direction: BingxueDirection
  direction_jp: string
  tier: BingxueTier
  description: string    // CHT with {var:}/{status:}/{scale:} template
  description_jp: string
  vars: Record<string, any>
}

// Per-hero available bingxue: CHT direction → {major, minor} JP name arrays.
// Each direction offers 3 majors + 6 minors for the hero to pick from.
export type HeroBingxue = Record<BingxueDirection, { major: string[]; minor: string[] }>

export interface Hero {
  name: string
  name_jp?: string | null
  aliases?: string[]
  // Official cfg.json numeric id (Sialia). Missing on override-only entries.
  cfg_id?: number

  faction: string
  clan?: string
  cost: number
  rarity: number | string
  gender?: string
  portrait: string
  detail_url?: string
  unique_skill?: string | null
  teachable_skill?: string | null
  assembly_skill?: string | null
  stats?: {
    lea: number
    val: number
    int: number
    pol: number
    cha: number
    spd: number
  }
  traits?: Trait[]
  bingxue?: HeroBingxue | null
}

import heroesData from '../../.build/heroes.json'
import skillsData from '../../.build/skills.json'
import statusesData from '../../.build/statuses.json'
import bingxueData from '../../.build/bingxue.json'

const heroes = ref<Hero[]>(heroesData && Array.isArray(heroesData) ? (heroesData as unknown as Hero[]) : [])
const skills = ref<Skill[]>(skillsData && Array.isArray(skillsData) ? (skillsData as unknown as Skill[]) : [])
const statuses = ref<Record<string, any>>(statusesData || {})
const bingxue = ref<Record<string, BingxueOption>>(
  (bingxueData as Record<string, BingxueOption>) || {}
)

export function useData() {
  return { heroes, skills, statuses, bingxue }
}