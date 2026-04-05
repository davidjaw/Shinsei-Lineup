import { ref } from 'vue'

// === Battle Engine Types (Flat & Atomic Design) ===

export type SkillType = 'Assault' | 'Command' | 'Active' | 'Passive' | string;

export type TriggerEvent =
  | 'battleStart'
  | 'turnStart'
  | 'beforeAction'
  | 'afterAction'
  | 'afterAttack'
  | 'onDamaged'
  | 'onHeal'
  | 'always'
  | string;

// Formula: "150 + caster.val * 1.5"
export type Formula = number | string;

// 屬性包含：統帥, 武勇, 智略, 政務, 魅力, 速度
export type Stat = 'lea' | 'val' | 'int' | 'pol' | 'cha' | 'spd' | 'damageDealt' | 'damageTaken' | 'strategyDamageDealt' | 'attackDamage';

export interface Scaling {
  stat: Stat;
  ratio: number;
}

// === Target Definition ===
export type TargetSide = 'ally' | 'enemy';
export type TargetScope = 'single' | 'group' | 'all';
export type TargetSelect = 'random' | 'lowestHp' | 'highestStat' | 'lowestStat';

export type TargetDef = 
  | 'self'
  | 'currentTarget'
  | { 
      side: TargetSide; 
      scope?: TargetScope; 
      count?: number | [number, number]; 
      select?: TargetSelect;
      stat?: Stat; 
      filter?: Condition; 
    };

// === Condition Definition ===
export type Condition =
  | { type: 'hasStatus'; status: string; invert?: boolean }
  | { type: 'turn'; value: number | number[] }
  | { type: 'turnRange'; min?: number; max?: number }
  | { type: 'chance'; value: number; scale?: Scaling }
  | { type: 'stat'; stat: Stat; op: '>' | '<' | '>='; value: number | 'highest' | 'lowest' }
  | { type: 'stackCount'; key: string; op: '>' | '<' | '>='; value: number }
  | { type: 'isCommander'; invert?: boolean }
  | { type: 'isGeneralRole'; role: 'main' | 'vice' };

// === Effect Definition ===
export type Effect =
  | { type: 'damage'; damageType: 'physical' | 'strategy' | 'true'; value: Formula }
  | { type: 'heal'; value: Formula }
  | { type: 'applyStatus'; status: string; duration: number; chance?: number }
  | { type: 'removeStatus'; status: string }
  | { type: 'buff'; stat: Stat; value: Formula; duration: number }
  | { type: 'addStack'; key: string; value?: number; max?: number }
  | { type: 'clearStack'; key: string }
  | { type: 'consumeStack'; key: string; thenDo?: Action[] }
  | { type: 'sequence'; actions: Action[] };

export interface Action {
  when?: Condition[];
  to: TargetDef;
  do: Effect;
  else?: Action[];
}

export interface SkillVar {
  base: number;
  max: number;
  scale?: string;
}

export interface Skill {
  id: string;
  name: string;
  name_jp?: string;
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
  brief_description?: string;
  related_stats?: string[];
  rate?: [number, number];
  cooldown?: number;
  maxPerTurn?: number;
  trigger?: TriggerEvent;
  do?: Action[];
  bonus?: {
    commander?: Action[];
    characters?: Record<string, Action[]>;
  };
}

export interface Trait {
  name: string
  rank: 'S' | 'A' | 'B' | 'C'
  active: boolean
  description?: string
}

export interface Hero {
  name: string
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
}

import heroesData from '../../.build/heroes.json'
import skillsData from '../../.build/skills.json'
import statusesData from '../../.build/statuses.json'

const DEFAULT_ICONS: Record<string, string> = {
  '指揮': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_zh_kongzhi.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
  '能動': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_zd_bingren_single.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
  '主動': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_zd_bingren_single.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
  '突撃': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_tj_bingren_single.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
  '突擊': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_tj_bingren_single.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
  '受動': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_bd_zengyi.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
  '被動': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_bd_zengyi.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
  '兵種': 'https://p11386-media-cdn.sialiagames.com.tw/meta_10000270/1765785439101/res/ui/icon/skill/icon_skill_tsbz_chibeidui.png?x-oss-process=image/format,webp/interlace,1/quality,Q_80/resize,w_164&t=1',
};

const heroes = ref<Hero[]>(heroesData && Array.isArray(heroesData) ? (heroesData as unknown as Hero[]) : [])
const skills = ref<Skill[]>(skillsData && Array.isArray(skillsData) ? (skillsData as unknown as Skill[]).map(s => ({
  ...s,
  icon: s.icon || DEFAULT_ICONS[s.type] || ''
})) : [])
const statuses = ref<Record<string, any>>(statusesData || {})

const loading = ref(false)

export function useData() {
  const fetchAllData = async () => {
    loading.value = false
  }
  return { heroes, skills, statuses, loading, fetchAllData }
}