<template>
  <div class="team-preview" :class="[`team-preview--${density}`, { 'team-preview--flush': !bordered }]">
    <div v-if="showHeader" class="header">
      <div class="title-wrap">
        <!-- title-prefix slot: optional chip/badge that sits left of the
             title-bar (ProposalCard uses this for the visibility toggle).
             Stays out of layout when no slot is filled. -->
        <slot name="title-prefix" />
        <span class="title-bar" />
        <span class="title font-brand">{{ resolvedTitle }}</span>
        <div v-if="activeTroops.length > 0" class="troop-chips">
          <span v-for="t in activeTroops" :key="t.key" class="troop-chip">
            {{ t.label }}{{ t.lv }}
          </span>
        </div>
      </div>
      <span class="cost">{{ totalCost }} <span class="cost-unit">Cost</span></span>
    </div>

    <div v-if="showWatermark" class="watermark watermark--header">
      <span class="watermark-line" />
      <span class="watermark-stamp">
        <span class="watermark-icon font-brand">猫</span>
        <span class="watermark-text font-brand">真戰配將</span>
      </span>
    </div>

    <div class="hero-row">
      <div v-for="(role, i) in roles" :key="i" class="hero-col">
        <div class="hero-meta">
          <span class="role-tag" :class="`role-tag--${role.key}`">{{ role.label }}</span>
          <template v-if="role.data.hero">
            <span class="cost-pill">{{ role.data.hero.cost }}C</span>
            <span v-if="!hideHeroArt" class="rarity">{{ rarityStars(role.data.hero.rarity) }}</span>
            <span v-if="role.data.breakthrough > 0" class="break-tag">突{{ role.data.breakthrough }}</span>
          </template>
        </div>
        <PreviewPortrait
          v-if="!hideHeroArt"
          :src="role.data.hero?.portrait ?? null"
          :alt="role.data.hero?.name"
          :render="portraitSize"
          class="portrait"
        />
        <div class="hero-name">{{ role.data.hero?.name ?? '—' }}</div>
      </div>
    </div>

    <div class="skill-grid">
      <div v-for="(role, i) in roles" :key="`s-${i}`" class="skill-col">
        <el-tooltip
          :content="uniqueSkills[i]?.brief_description || ''"
          :disabled="!uniqueSkills[i]?.brief_description"
          placement="top"
          effect="dark"
        >
          <div class="skill-name skill-name--unique" :class="{ 'skill-name--empty': !uniqueSkills[i] }">
            <span class="own-tag">自</span>
            <span class="skill-text">{{ uniqueSkills[i]?.name ?? '—' }}</span>
          </div>
        </el-tooltip>
        <el-tooltip
          :content="role.data.skill1?.brief_description || ''"
          :disabled="!role.data.skill1?.brief_description"
          placement="top"
          effect="dark"
        >
          <div
            class="skill-name"
            :class="{
              'skill-name--empty': !role.data.skill1,
              'skill-name--meta': isMetaSkill(role.data.skill1),
            }"
          >
            {{ role.data.skill1?.name ?? '—' }}
          </div>
        </el-tooltip>
        <el-tooltip
          :content="role.data.skill2?.brief_description || ''"
          :disabled="!role.data.skill2?.brief_description"
          placement="top"
          effect="dark"
        >
          <div
            class="skill-name"
            :class="{
              'skill-name--empty': !role.data.skill2,
              'skill-name--meta': isMetaSkill(role.data.skill2),
            }"
          >
            {{ role.data.skill2?.name ?? '—' }}
          </div>
        </el-tooltip>
      </div>
    </div>

    <div v-if="hasAnyBingxue" class="bingxue-row">
      <div v-for="(role, i) in roles" :key="`b-${i}`" class="bingxue-col">
        <div
          v-if="role.data.bingxue.direction"
          class="bingxue-box"
          :data-dir="role.data.bingxue.direction"
        >
          <div class="bingxue-header">
            <span class="bingxue-dir">{{ role.data.bingxue.direction }}</span>
            <span class="bingxue-major">{{ role.data.bingxue.major ? bingxueName(role.data.bingxue.major) : '—' }}</span>
          </div>
          <div v-if="role.data.bingxue.minors.length" class="bingxue-minors">
            <span
              v-for="(m, j) in role.data.bingxue.minors"
              :key="`${m.name}-${j}`"
              class="bingxue-minor"
            >
              {{ bingxueName(m.name) }} {{ roman(m.level) }}
            </span>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { computeTeamCost, type Lineup } from '../../composables/useLineups'
import { useData, type Skill } from '../../composables/useData'
import { useTroopLevels } from '../../composables/useTroopLevels'
import { TROOP_TYPES, TROOP_LABELS } from '../../constants/traits'
import PreviewPortrait from './PreviewPortrait.vue'

const { skills, bingxue: bingxueCatalog } = useData()

// Resolve a hero's `unique_skill` string into the full Skill object so we
// can surface its brief_description in the tooltip. Match by CHT name first
// then JP — same fallback as LineupSlot.uniqueSkillData.
const findSkillByName = (name: string | null | undefined): Skill | null => {
  if (!name) return null
  return skills.value.find(s => s.name === name || s.name_jp === name) ?? null
}

const isMetaSkill = (s: Skill | null | undefined): boolean =>
  s?.type === '兵種' || s?.type === '陣法'

const props = withDefaults(defineProps<{
  team: Lineup
  density?: 'compact' | 'regular'
  title?: string
  showHeader?: boolean
  showWatermark?: boolean
  bordered?: boolean
  /** Hide portrait + rarity stars together (screenshot density toggle). */
  hideHeroArt?: boolean
}>(), {
  density: 'regular',
  showHeader: true,
  showWatermark: true,
  bordered: true,
  hideHeroArt: false,
})

const portraitSize = computed(() => props.density === 'compact' ? 104 : 166)

const roles = computed(() => [
  { key: 'main', label: '主將', data: props.team.main },
  { key: 'vice1', label: '副將', data: props.team.vice1 },
  { key: 'vice2', label: '副將', data: props.team.vice2 },
])

const totalCost = computed(() => computeTeamCost(props.team))

const uniqueSkills = computed(() =>
  roles.value.map(r => findSkillByName(r.data.hero?.unique_skill)),
)

const resolvedTitle = computed(() => props.title ?? props.team.name ?? '未命名隊伍')

// Team-level troop affinity aggregated across heroes (respects breakthrough
// gates via useTroopLevels). Only show chips for levels > 0 to keep the
// header tidy when no relevant traits are unlocked yet.
const teamRef = computed(() => props.team)
const troopLevels = useTroopLevels(teamRef)
const activeTroops = computed(() =>
  TROOP_TYPES
    .filter(tt => troopLevels.value[tt] > 0)
    .map(tt => ({ key: tt, label: TROOP_LABELS[tt], lv: troopLevels.value[tt] })),
)

const rarityStars = (rarity: number | string): string => {
  const n = typeof rarity === 'number' ? rarity : Number(rarity) || 0
  if (!n) return ''
  return '★'.repeat(Math.min(5, n)) + '☆'.repeat(Math.max(0, 5 - n))
}

// Bingxue read-only display — mirrors BingxueSection's filled-state layout
// (direction-colored header bar with major skill + per-minor chips). Wrapped
// row only renders if any of the three heroes has a direction selected.
const bingxueName = (jp: string): string => bingxueCatalog.value[jp]?.name ?? jp
const roman = (n: number): string => ['', 'I', 'II', 'III', 'IV', 'V'][n] ?? String(n)
const hasAnyBingxue = computed(() =>
  roles.value.some(r => r.data.bingxue.direction),
)
</script>

<style scoped>
.team-preview {
  background: linear-gradient(180deg, #FFFBF1 0%, #FFFFFF 18%, #FFFFFF 100%);
  border: 1px solid rgb(var(--color-divider));
  border-radius: 12px;
  padding: 18px;
  position: relative;
  font-family: ui-sans-serif, system-ui, sans-serif;
  color: rgb(var(--color-ink));
  box-shadow: inset 0 1px 0 rgba(180, 83, 9, 0.08);
}
.team-preview--compact { padding: 10px; }

/* Flush variant: drop the standalone framing so a wrapping card can own the
   bounding visual. Keeps the amber gradient background that gives the
   preview its identity. */
.team-preview--flush {
  border: none;
  border-radius: 0;
  box-shadow: none;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.team-preview--compact .header { gap: 6px; }
/* When the watermark sits directly under the header it replaces what was
   originally a hairline border — collapse the gap so the line/stamp reads
   as the header's underscore. */
.watermark--header { margin-top: 6px; margin-bottom: 10px; }
.team-preview--compact .watermark--header { margin-top: 4px; margin-bottom: 6px; }
.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex-wrap: wrap;
}
.title-bar {
  width: 5px;
  height: 23px;
  background: #b45309;
  border-radius: 2px;
  flex-shrink: 0;
}
.title { font-size: 23px; font-weight: 700; color: rgb(var(--color-ink)); }
.team-preview--compact .title { font-size: 20px; }
.team-preview--compact .title-bar { height: 21px; width: 4px; }

.troop-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.troop-chip {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgb(var(--color-highlight));
  color: rgb(var(--color-focus));
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.3px;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.team-preview--compact .troop-chip { font-size: 11px; padding: 2px 6px; }

.cost {
  font-size: 25px;
  font-weight: 700;
  color: #b45309;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.team-preview--compact .cost { font-size: 21px; }
.cost-unit {
  font-size: 14px;
  color: rgb(var(--color-ink-mute));
  font-weight: 600;
  margin-left: 3px;
}
.team-preview--compact .cost-unit { font-size: 12px; }

.hero-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.team-preview--compact .hero-row { gap: 5px; }
.team-preview--compact .hero-col { gap: 3px; }
.hero-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}
.hero-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 7px;
  font-size: 14px;
  line-height: 1;
  min-height: 24px;
}
.team-preview--compact .hero-meta { gap: 4px; min-height: 20px; font-size: 11px; }
.role-tag {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.5px;
}
.team-preview--compact .role-tag { font-size: 10px; padding: 2px 6px; }
.role-tag--main {
  background: linear-gradient(135deg, #b45309 0%, #92400e 100%);
  color: #fff;
}
.role-tag--vice1, .role-tag--vice2 {
  background: rgb(var(--color-surface-muted));
  color: rgb(var(--color-ink));
  border: 1px solid rgb(var(--color-divider));
}
.cost-pill {
  display: inline-block;
  padding: 3px 7px;
  border-radius: 4px;
  background: #fef3c7;
  color: #92400e;
  font-weight: 700;
  font-size: 13px;
}
.team-preview--compact .cost-pill { font-size: 10px; padding: 2px 5px; }
.rarity { color: #f59e0b; letter-spacing: -1px; font-size: 16px; }
.team-preview--compact .rarity { font-size: 12px; }
.break-tag {
  display: inline-block;
  padding: 3px 7px;
  border-radius: 4px;
  background: #fce7f3;
  color: #be185d;
  font-weight: 700;
  font-size: 13px;
}
.team-preview--compact .break-tag { font-size: 10px; padding: 2px 5px; }

.portrait {
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px rgb(var(--color-divider));
}
.hero-name {
  font-size: 20px;
  font-weight: 700;
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgb(var(--color-ink));
}
.team-preview--compact .hero-name { font-size: 17px; }

.skill-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 1px solid rgb(var(--color-divider));
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  margin-top: 4px;
}
.skill-col {
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgb(var(--color-divider));
}
.skill-col:last-child { border-right: none; }
.skill-name {
  font-size: 17px;
  font-weight: 500;
  padding: 9px 8px;
  text-align: center;
  border-bottom: 1px solid rgb(var(--color-divider));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
  transition: background 0.12s ease;
}
.skill-name:last-child { border-bottom: none; }
.skill-name:hover { background: rgb(var(--color-highlight)); }
.skill-name--empty { color: rgb(var(--color-ink-mute)); cursor: default; }
.team-preview--compact .skill-name { font-size: 14px; padding: 5px 5px; }

/* 兵種 / 陣法 skills — bold inline rather than lifted into a separate
   summary row. Subtle amber tint distinguishes them from generic skills
   without adding visual noise. */
.skill-name--meta { font-weight: 700; background: rgba(180, 83, 9, 0.05); }
.skill-name--meta:hover { background: rgba(180, 83, 9, 0.12); }

/* 自帶戰法 row: tinted background + leading badge to distinguish from
   user-chosen skill1/skill2. Sits at the top of each column. */
.skill-name--unique {
  background: rgba(180, 83, 9, 0.06);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.skill-name--unique:hover { background: rgba(180, 83, 9, 0.12); }
.own-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 21px;
  height: 21px;
  border-radius: 4px;
  background: #b45309;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.skill-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.team-preview--compact .own-tag { width: 18px; height: 18px; font-size: 12px; }

/* Bingxue row — 3 columns aligned to the hero columns above. Each box
   mirrors BingxueSection's filled-state visual: direction-colored header
   bar with major skill + minor chips below. Direction palette matches the
   game UI (red/amber/purple/emerald). */
.bingxue-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 6px;
}
.team-preview--compact .bingxue-row { gap: 5px; margin-top: 4px; }
.bingxue-box {
  border: 1px solid;
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}
.bingxue-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  color: #fff;
  font-weight: 700;
  min-width: 0;
}
.bingxue-dir {
  font-size: 11px;
  opacity: 0.85;
  flex-shrink: 0;
}
.bingxue-major {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bingxue-minors {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  padding: 4px;
  background: #fff;
}
.bingxue-minor {
  font-size: 11px;
  padding: 2px 5px;
  border-radius: 3px;
  border: 1px solid;
  white-space: nowrap;
  font-weight: 600;
}

.bingxue-box[data-dir="武略"] { border-color: #fca5a5; }
.bingxue-box[data-dir="武略"] .bingxue-header { background: #ef4444; }
.bingxue-box[data-dir="武略"] .bingxue-minor { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }

.bingxue-box[data-dir="陣立"] { border-color: #fcd34d; }
.bingxue-box[data-dir="陣立"] .bingxue-header { background: #d97706; }
.bingxue-box[data-dir="陣立"] .bingxue-minor { background: #fef3c7; border-color: #fcd34d; color: #92400e; }

.bingxue-box[data-dir="機略"] { border-color: #d8b4fe; }
.bingxue-box[data-dir="機略"] .bingxue-header { background: #a855f7; }
.bingxue-box[data-dir="機略"] .bingxue-minor { background: #f3e8ff; border-color: #d8b4fe; color: #6b21a8; }

.bingxue-box[data-dir="臨戰"] { border-color: #6ee7b7; }
.bingxue-box[data-dir="臨戰"] .bingxue-header { background: #10b981; }
.bingxue-box[data-dir="臨戰"] .bingxue-minor { background: #d1fae5; border-color: #6ee7b7; color: #065f46; }

.team-preview--compact .bingxue-header { padding: 3px 6px; }
.team-preview--compact .bingxue-major { font-size: 11px; }
.team-preview--compact .bingxue-dir { font-size: 9px; }
.team-preview--compact .bingxue-minors { padding: 3px; gap: 2px; }
.team-preview--compact .bingxue-minor { font-size: 10px; padding: 1px 4px; }

/* Watermark — in-flow footer row instead of an absolute overlay so it never
   collides with the bingxue strip above. Echoes the sidebar brand glyph
   (circled 猫) for visual identity. */
.watermark {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}
.watermark-line {
  flex: 1;
  height: 1px;
  /* Solid amber on the left half, fade to transparent on the right so the
     line softly kisses the stamp instead of slamming into it at full alpha. */
  background: linear-gradient(to right,
    rgba(180, 83, 9, 0.3),
    rgba(180, 83, 9, 0.3) 50%,
    transparent);
}
.watermark-stamp {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  pointer-events: none;
}
.watermark-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1.5px solid #b45309;
  background: transparent;
  color: #b45309;
  font-weight: 700;
  font-size: 13px;
  line-height: 1;
}
.watermark-text {
  font-weight: 700;
  color: #b45309;
  font-size: 13px;
  letter-spacing: 3px;
}
.team-preview--compact .watermark { margin-top: 6px; gap: 6px; }
.team-preview--compact .watermark-icon {
  width: 17px;
  height: 17px;
  font-size: 10px;
  border-width: 1px;
}
.team-preview--compact .watermark-text { font-size: 10px; letter-spacing: 2px; }
</style>
