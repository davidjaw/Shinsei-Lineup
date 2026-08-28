<template>
  <div class="flex-1 overflow-y-auto p-4 md:p-6">
    <div class="max-w-7xl">
      <el-tabs v-model="activeTab" class="mt-1">
        <el-tab-pane label="公開精選" name="public">
          <!-- Toolbar: just the hero filter + page-level sort. Filter has no
               leading label — its placeholder carries the intent. Sort lives
               here when no HeroSet is open; once the split view opens, the
               variant-scope sort moves into the main pane (compact second
               line) and this row keeps the page-level (HeroSet) sort. -->
          <div class="toolbar">
            <el-select
              v-model="selectedHeroes"
              multiple
              collapse-tags
              collapse-tags-tooltip
              filterable
              placeholder="武將篩選"
              class="hero-filter"
              clearable
            >
              <el-option
                v-for="h in heroOptions"
                :key="h.value"
                :label="h.label"
                :value="h.value"
              />
            </el-select>
            <SortPills
              v-model="heroSetSort"
              :options="heroSetSortOptions"
              aria-label="英雄組合排序"
            />
            <span v-if="selectedHeroes.length > 0" class="filter-hint">
              篩出 <strong>{{ filteredHeroSets.length }}</strong> 組
            </span>
          </div>

          <!-- Default state: full-width grid of HeroSet cards. -->
          <div v-if="!activeHeroSetHash" v-loading="loadingSets" class="min-h-[240px]">
            <p
              v-if="!loadingSets && filteredHeroSets.length === 0"
              class="empty-state"
            >
              {{ heroSets.length === 0
                ? '目前還沒有公開的精選隊伍。'
                : '篩選後沒有符合的英雄組合。' }}
            </p>
            <div v-else class="hero-set-grid">
              <HeroSetCard
                v-for="s in filteredHeroSets"
                :key="s.heroSetHash"
                :summary="s"
                @open="openHeroSet(s.heroSetHash)"
              />
            </div>
          </div>

          <!-- Variants view: sidebar list + main variants grid. -->
          <div v-else class="split-layout">
            <aside class="set-sidebar">
              <header class="sidebar-head">
                <span class="sidebar-title">英雄組合</span>
                <span class="sidebar-count">{{ filteredHeroSets.length }}</span>
              </header>
              <div class="sidebar-list">
                <button
                  v-for="s in filteredHeroSets"
                  :key="s.heroSetHash"
                  type="button"
                  class="sidebar-item"
                  :class="{ 'sidebar-item--active': s.heroSetHash === activeHeroSetHash }"
                  @click="openHeroSet(s.heroSetHash)"
                >
                  <div class="sidebar-names">
                    <span class="sidebar-name sidebar-name--main">
                      {{ s.sampleTeam?.main?.hero?.name ?? '—' }}
                    </span>
                    <span class="sidebar-sep">·</span>
                    <span class="sidebar-name">{{ sortedViceName(s, 0) }}</span>
                    <span class="sidebar-sep">·</span>
                    <span class="sidebar-name">{{ sortedViceName(s, 1) }}</span>
                  </div>
                  <div class="sidebar-stats">
                    <span class="sidebar-stat">
                      <strong>{{ s.variantCount }}</strong> 變體
                    </span>
                    <span class="sidebar-stat sidebar-stat--up">
                      <el-icon :size="10"><CaretTop /></el-icon>
                      <strong>{{ s.totalUpvoteCount }}</strong>
                    </span>
                    <span
                      class="sidebar-stat"
                      :class="setTrendClass(s.recentVoteDelta)"
                    >
                      <el-icon :size="10"><component :is="setTrendIcon(s.recentVoteDelta)" /></el-icon>
                      <strong>{{ setTrendText(s.recentVoteDelta) }}</strong>
                    </span>
                  </div>
                </button>
              </div>
            </aside>

            <main class="variants-main">
              <header class="variants-head" v-if="activeHeroSet">
                <div class="head-row head-row--portraits">
                  <button
                    type="button"
                    class="back-btn"
                    aria-label="返回列表"
                    title="返回列表"
                    @click="closeHeroSet"
                  >
                    <el-icon :size="16"><ArrowLeftBold /></el-icon>
                  </button>
                  <div class="head-portraits">
                    <div class="portrait-cell portrait-cell--main">
                      <PreviewPortrait :src="activeMainHero?.portrait ?? null" :alt="activeMainHero?.name" :render="76" />
                    </div>
                    <div
                      v-for="(v, idx) in activeViceHeroes"
                      :key="`vh-${idx}`"
                      class="portrait-cell"
                    >
                      <PreviewPortrait :src="v?.portrait ?? null" :alt="v?.name" :render="76" />
                    </div>
                  </div>
                  <div class="head-stats">
                    <span class="head-stat">
                      <strong>{{ activeHeroSet.variantCount }}</strong>
                      <span class="head-stat-label">變體</span>
                    </span>
                    <span class="head-stat-divider" />
                    <span class="head-stat head-stat--up">
                      <el-icon :size="13"><CaretTop /></el-icon>
                      <strong>{{ activeHeroSet.totalUpvoteCount }}</strong>
                      <span class="head-stat-label">總贊</span>
                    </span>
                    <span class="head-stat-divider" />
                    <span class="head-stat" :class="trendClass">
                      <el-icon :size="13"><component :is="trendIcon" /></el-icon>
                      <strong>{{ trendDisplay }}</strong>
                      <span class="head-stat-label">近30天</span>
                    </span>
                  </div>
                </div>
                <!-- Second line: variant-scope sort + insight chip. Compact
                     so the portraits row above stays the focal point. -->
                <div class="head-row head-row--controls">
                  <SortPills
                    v-model="variantSort"
                    :options="variantSortOptions"
                    aria-label="變體排序"
                  />
                  <span v-if="consensusInfo" class="consensus-chip" :title="consensusInfo.tooltip">
                    {{ consensusInfo.label }}
                  </span>
                </div>
              </header>

              <div v-loading="loadingVariants" class="variants-grid">
                <p v-if="!loadingVariants && activeVariants.length === 0" class="empty-state empty-state--inline">
                  這個英雄組合還沒有變體。
                </p>
                <VariantCard
                  v-for="v in activeVariants"
                  :key="v.id"
                  :variant="v"
                  :first-author-name="resolveAuthorName(v.firstAuthorId)"
                  :contributors="contributorsByVariant.get(v.id)"
                  :voted-direction="myVotes.get(v.id) ?? null"
                  :is-my-contribution="myContributions.has(v.id)"
                  :is-logged-in="isLoggedIn"
                  @upvote="onVariantVote(v.id, 1)"
                  @downvote="onVariantVote(v.id, -1)"
                  @import-to-group="onImportVariantToGroup(v)"
                  @withdraw="onWithdrawVariant(v)"
                />
              </div>
            </main>
          </div>
        </el-tab-pane>

        <el-tab-pane label="我的提案" name="mine" :disabled="!isLoggedIn">
          <div v-if="!isLoggedIn" class="empty-state">
            登入後可管理自己的提案。
          </div>
          <div v-else v-loading="loadingMine" class="min-h-[160px]">
            <p
              v-if="!loadingMine && myProposals.length === 0"
              class="empty-state"
            >
              還沒有任何提案。在配將模擬完成隊伍後，從側欄「另存為精選隊伍」建立。
            </p>
            <div v-else class="proposal-grid">
              <ProposalCard
                v-for="p in myProposals"
                :key="p.id"
                :proposal="p"
                :can-edit="true"
                @toggle-public="onTogglePublic(p)"
                @delete="onDelete(p)"
              />
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <ExportTeamToGroupDialog
      v-model="exportDialogVisible"
      variant="import"
      :source="exportSource"
      :default-group-id="currentGroup?.id"
      @exported="onExported"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch, markRaw, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CaretTop, Top, Bottom, Minus, Clock,
  TrendCharts, Tickets, Calendar, ArrowLeftBold,
} from '@element-plus/icons-vue'
import { useVariants } from '../composables/useVariants'
import { useProposals } from '../composables/useProposals'
import { useAuth } from '../composables/useAuth'
import { useData } from '../composables/useData'
import { useGroups } from '../composables/useGroups'
import { useGroupPersistence } from '../composables/useGroupPersistence'
import { useDialogs } from '../composables/useDialogs'
import { useLineups } from '../composables/useLineups'
import type { Proposal, ImportConflictResolution } from '../types/group'
import type { HeroSetSummary, Variant, VoteDirection } from '../lib/variants'
import { sortedViceHeroes, snapshotTeam } from '../lib/lineup'
import { applyConflictResolution } from '../lib/teamConflicts'
import HeroSetCard from '../components/preview/HeroSetCard.vue'
import VariantCard from '../components/preview/VariantCard.vue'
import PreviewPortrait from '../components/preview/PreviewPortrait.vue'
import SortPills from '../components/variants/SortPills.vue'
import ProposalCard from '../components/preview/ProposalCard.vue'
import ExportTeamToGroupDialog, { type ExportSource } from '../components/dialogs/ExportTeamToGroupDialog.vue'
import type { HeroSetSort } from '../composables/useVariants'
import type { VariantSort } from '../lib/variants'

const route = useRoute()
const router = useRouter()
const { isLoggedIn } = useAuth()
const { heroes } = useData()
const {
  heroSets, sortedHeroSets, activeHeroSetHash, activeHeroSet, activeVariants,
  contributorsByVariant,
  myVotes, myContributions, heroSetSort, variantSort,
  loadingSets, loadingVariants,
  refreshHeroSets, selectHeroSet, fetchContributors,
  vote, withdraw,
} = useVariants()
const {
  myProposals, loadingMine,
  refreshMine, togglePublic, remove,
} = useProposals()

const activeTab = ref<'public' | 'mine'>(isLoggedIn.value ? 'mine' : 'public')
const selectedHeroes = ref<string[]>([])

// Sort option metadata. `markRaw` on the icon component avoids Vue reactivity
// warnings about the icon being treated as a reactive ref.
const heroSetSortOptions: Array<{ value: HeroSetSort; label: string; icon?: Component }> = [
  { value: 'total',  label: '綜合分', icon: markRaw(TrendCharts) },
  { value: 'recent', label: '近30天', icon: markRaw(Calendar) },
  { value: 'latest', label: '最新',   icon: markRaw(Clock) },
  { value: 'count',  label: '變體數', icon: markRaw(Tickets) },
]
const variantSortOptions: Array<{ value: VariantSort; label: string; icon?: Component }> = [
  { value: 'votes',  label: '投票', icon: markRaw(CaretTop) },
  { value: 'latest', label: '最新', icon: markRaw(Clock) },
]

onMounted(async () => {
  await refreshHeroSets()
  if (isLoggedIn.value) void refreshMine()

  // Restore split-view selection from URL on cold load.
  const setParam = (route.query.set as string | undefined) ?? null
  if (setParam && heroSets.value.some(s => s.heroSetHash === setParam)) {
    await openHeroSet(setParam)
  }
})

watch(isLoggedIn, (loggedIn) => {
  if (loggedIn && activeTab.value === 'public') activeTab.value = 'mine'
  if (loggedIn) void refreshMine()
})

const heroOptions = computed(() => {
  const numericRarity = (r: number | string | undefined): number =>
    typeof r === 'number' ? r : Number(r) || 0
  return [...heroes.value]
    .sort((a, b) => numericRarity(b.rarity) - numericRarity(a.rarity) || (b.cost ?? 0) - (a.cost ?? 0))
    .map(h => ({ value: h.name, label: h.name }))
})

const filteredHeroSets = computed(() => {
  if (selectedHeroes.value.length === 0) return sortedHeroSets.value
  const wanted = new Set(selectedHeroes.value)
  return sortedHeroSets.value.filter(s => {
    const t = s.sampleTeam
    const names = [t?.main?.hero?.name, t?.vice1?.hero?.name, t?.vice2?.hero?.name]
    return names.some(n => n && wanted.has(n))
  })
})

// Sidebar vice-name helper — uses the shared canonical sort so list order
// matches the variant cards' column rhythm.
const sortedViceName = (s: HeroSetSummary, idx: 0 | 1): string => {
  const vices = sortedViceHeroes(s.sampleTeam)
  return vices[idx]?.name ?? '—'
}

const setTrendIcon = (delta: number) => delta > 0 ? Top : delta < 0 ? Bottom : Minus
const setTrendClass = (delta: number) => ({
  'sidebar-stat--trend-up':   delta > 0,
  'sidebar-stat--trend-down': delta < 0,
  'sidebar-stat--trend-flat': delta === 0,
})
const setTrendText = (delta: number): string =>
  delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '0'

// Active HeroSet header derived values.
const activeMainHero = computed(() => activeHeroSet.value?.sampleTeam?.main?.hero ?? null)
const activeViceHeroes = computed(() => sortedViceHeroes(activeHeroSet.value?.sampleTeam))

const delta = computed(() => activeHeroSet.value?.recentVoteDelta ?? 0)
const trendIcon = computed(() => setTrendIcon(delta.value))
const trendClass = computed(() => ({
  'head-stat--trend-up':   delta.value > 0,
  'head-stat--trend-down': delta.value < 0,
  'head-stat--trend-flat': delta.value === 0,
}))
const trendDisplay = computed(() => setTrendText(delta.value))

// Consensus/divergence insight chip. Suppressed when there's not enough
// signal (< 2 variants, < 10 total votes).
const consensusInfo = computed<{ label: string; tooltip: string } | null>(() => {
  if (activeVariants.value.length < 2) return null
  const total = activeVariants.value.reduce((s, v) => s + v.upvoteCount, 0)
  if (total < 10) return null
  const top = Math.max(...activeVariants.value.map(v => v.upvoteCount))
  const share = top / total
  if (share >= 0.6) {
    return {
      label: '共識型',
      tooltip: `頂部變體佔 ${Math.round(share * 100)}% 贊數 — 玩家普遍認同單一配法`,
    }
  }
  if (share < 0.4) {
    return {
      label: '分歧型',
      tooltip: '贊數分散於多個變體 — 仍在被積極研究的活躍 meta',
    }
  }
  return null
})

// ---------------------------------------------------------------------------
// Open / close transitions for the split-view selection.

const openHeroSet = async (hash: string): Promise<void> => {
  await selectHeroSet(hash)
  void router.replace({ query: { ...route.query, set: hash } })
  // Prefetch contributors for every variant in parallel — sequential awaits
  // turned 10 variants into 10 serial round-trips and stalled the drawer
  // open. fetchContributors is itself cache-aware (skips already-loaded ids),
  // so re-opens of the same HeroSet are free.
  await Promise.all(
    activeVariants.value
      .filter(v => !contributorsByVariant.value.has(v.id))
      .map(v => fetchContributors(v.id)),
  )
}

const closeHeroSet = (): void => {
  activeHeroSetHash.value = null
  const next = { ...route.query }
  delete next.set
  void router.replace({ query: next })
}

// ---------------------------------------------------------------------------
// Variant interactions.

const onVariantVote = async (id: string, direction: VoteDirection): Promise<void> => {
  if (!isLoggedIn.value) {
    ElMessage.warning('請先登入')
    return
  }
  try { await vote(id, direction) }
  catch (e) { ElMessage.error(`投票失敗：${(e as Error).message}`) }
}

const onWithdrawVariant = async (variant: Variant): Promise<void> => {
  try {
    const { deleted } = await withdraw(variant.id)
    ElMessage.success(deleted ? '已撤回，變體已刪除' : '已撤回你的提交')
  } catch (e) {
    ElMessage.error(`撤回失敗：${(e as Error).message}`)
  }
}

const resolveAuthorName = (authorId: string | null): string | null => {
  if (!authorId) return null
  for (const rows of contributorsByVariant.value.values()) {
    const match = rows.find(c => c.userId === authorId)
    if (match) return match.authorName
  }
  return null
}

// ---------------------------------------------------------------------------
// Import to group (shared between variant and proposal flows).

const dialogs = useDialogs()
const { groups, currentGroup, currentGroupIndex, appendTeamToGroup } = useGroups()
const { addTeamFromSnapshot } = useLineups()
const { flushLocalAutosave } = useGroupPersistence()
const exportDialogVisible = dialogs.useDialog('export-team-to-group')
const exportSource = ref<ExportSource | null>(null)

const onImportVariantToGroup = (variant: Variant): void => {
  const t = variant.team
  const name = [t.main?.hero?.name, t.vice1?.hero?.name, t.vice2?.hero?.name]
    .filter(Boolean).join(' + ') || '精選變體'
  exportSource.value = {
    team: snapshotTeam(t),
    displayName: name,
  }
  exportDialogVisible.value = true
}

const uniqueTeamName = (desired: string, taken: string[]): string => {
  const base = desired.replace(/\s*\(\d+\)\s*$/, '').trim() || desired
  if (!taken.includes(base)) return base
  for (let n = 2; n < 100; n++) {
    const candidate = `${base} (${n})`
    if (!taken.includes(candidate)) return candidate
  }
  return `${base} (${Date.now()})`
}

const onExported = ({
  destGroupIdx,
  resolution,
}: {
  destGroupIdx: number
  resolution: ImportConflictResolution
}): void => {
  const src = exportSource.value
  if (!src) return
  const destGroup = groups.value[destGroupIdx]
  if (!destGroup) return
  applyConflictResolution(src.team, destGroup.teams, resolution)
  src.team.name = uniqueTeamName(src.displayName, destGroup.teams.map((t) => t.name))
  const isCurrent = destGroupIdx === currentGroupIndex.value
  const ok = isCurrent
    ? addTeamFromSnapshot(src.team)
    : appendTeamToGroup(destGroupIdx, src.team)
  if (!ok) {
    ElMessage.error('該編組已滿，無法加入')
    return
  }
  flushLocalAutosave()
  exportSource.value = null
  ElMessage.success(`已將「${src.displayName}」匯入到「${destGroup.name}」`)
}

// ---------------------------------------------------------------------------
// My-proposals tab handlers.

const onTogglePublic = async (p: Proposal): Promise<void> => {
  const wasPublic = p.isPublic
  try {
    await togglePublic(p.id, !wasPublic)
    ElMessage.success(wasPublic ? '已設為私人' : '已公開')
    void refreshHeroSets()
  } catch (e) { ElMessage.error(`切換失敗：${(e as Error).message}`) }
}

const onDelete = async (p: Proposal): Promise<void> => {
  try {
    await remove(p.id)
    ElMessage.success('已刪除提案')
    // A public proposal's variant may have been withdrawn — refresh the feed.
    if (p.isPublic) void refreshHeroSets()
  } catch (e) { ElMessage.error(`刪除失敗：${(e as Error).message}`) }
}
</script>

<style scoped>
/* Toolbar: filter + sort + count, all on one row. Filter has no leading
   label (placeholder carries the intent), sort uses the shared SortPills. */
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 8px 0 14px;
}
.hero-filter {
  min-width: 260px;
  max-width: 420px;
  flex: 0 1 auto;
}
.filter-hint {
  font-size: 12px;
  color: rgb(var(--color-ink-mute));
}
.filter-hint strong {
  color: rgb(var(--color-ink));
  font-weight: 700;
}

/* Full-width hero set grid (no variants view open). */
.hero-set-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
@media (min-width: 768px)  { .hero-set-grid { grid-template-columns: repeat(3, 1fr); gap: 14px; } }
@media (min-width: 1024px) { .hero-set-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 1536px) { .hero-set-grid { grid-template-columns: repeat(5, 1fr); } }

/* Split layout: 268px sidebar + flexible main. On narrow viewports the
   sidebar hides and only the main pane shows (the back button returns to
   the full grid). */
.split-layout {
  display: grid;
  grid-template-columns: 268px 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 1023px) {
  .split-layout { grid-template-columns: 1fr; gap: 0; }
  .set-sidebar { display: none; }
}

/* Sidebar list ----------------------------------------------------------- */
.set-sidebar {
  background: #fff;
  border: 1px solid rgb(var(--color-divider));
  border-radius: 12px;
  overflow: hidden;
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
}
.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
  border-bottom: 1px solid rgb(var(--color-divider));
  background: linear-gradient(180deg, rgba(180, 83, 9, 0.04) 0%, transparent 100%);
}
.sidebar-title {
  font-size: 13px;
  font-weight: 700;
  color: rgb(var(--color-ink));
  letter-spacing: 1px;
}
.sidebar-count {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
  background: rgba(180, 83, 9, 0.08);
  padding: 1px 8px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}
.sidebar-list {
  flex: 1;
  overflow-y: auto;
}
.sidebar-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 14px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid rgb(var(--color-divider));
  transition: background 0.12s, padding-left 0.15s;
  font: inherit;
  color: inherit;
}
.sidebar-item:last-child { border-bottom: none; }
.sidebar-item:hover:not(.sidebar-item--active) {
  background: rgb(var(--color-highlight));
  padding-left: 16px;
}
/* Active item: amber left rail (3px) and warm tint background. The rail
   doubles as a "you are here" beacon when the user scrolls the list. */
.sidebar-item--active {
  background: linear-gradient(90deg, rgba(180, 83, 9, 0.10) 0%, rgba(180, 83, 9, 0.02) 100%);
  box-shadow: inset 3px 0 0 #b45309;
  padding-left: 16px;
}

.sidebar-names {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  font-size: 13px;
  color: rgb(var(--color-ink));
  line-height: 1.3;
}
.sidebar-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-name--main {
  color: #92400e;
  font-weight: 700;
}
.sidebar-sep { color: rgb(var(--color-ink-mute)); opacity: 0.5; }

.sidebar-stats {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: rgb(var(--color-ink-mute));
  font-variant-numeric: tabular-nums;
}
.sidebar-stat {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.sidebar-stat strong { color: rgb(var(--color-ink-soft)); font-weight: 700; }
.sidebar-stat--up { color: #b45309; }
.sidebar-stat--up strong { color: #92400e; }
.sidebar-stat--trend-up   { color: #15803d; }
.sidebar-stat--trend-up   strong { color: #166534; }
.sidebar-stat--trend-down { color: #b91c1c; }
.sidebar-stat--trend-down strong { color: #991b1b; }
.sidebar-stat--trend-flat { color: rgb(var(--color-ink-mute)); opacity: 0.7; }

/* Variants main pane --------------------------------------------------- */
.variants-main {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0; /* allow children to shrink within the grid track */
}
.variants-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  background: #ffffff;
  border: 1px solid rgba(180, 83, 9, 0.18);
  border-radius: 12px;
  box-shadow: 0 2px 6px rgba(180, 83, 9, 0.04);
}
.head-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.head-row--portraits { padding-right: 0; }
.head-row--controls {
  padding-top: 6px;
  border-top: 1px dashed rgb(var(--color-divider));
  gap: 10px;
}

.back-btn {
  width: 32px;
  height: 32px;
  border: 1px solid rgb(var(--color-divider));
  border-radius: 8px;
  background: #fff;
  color: rgb(var(--color-ink-soft));
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
  flex-shrink: 0;
}
.back-btn:hover {
  background: rgb(var(--color-highlight));
  color: rgb(var(--color-ink));
  border-color: rgba(180, 83, 9, 0.4);
}

.head-portraits {
  display: inline-flex;
  gap: 10px;
}
.portrait-cell { position: relative; }
.portrait-cell--main :deep(.preview-portrait) {
  box-shadow:
    0 0 0 2px #b45309,
    0 0 0 4px #fff,
    0 0 0 5px rgba(180, 83, 9, 0.2);
}

.head-stats {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  padding: 7px 14px;
  background: linear-gradient(90deg, rgba(180, 83, 9, 0.04) 0%, rgba(180, 83, 9, 0.08) 50%, rgba(180, 83, 9, 0.04) 100%);
  border: 1px solid rgba(180, 83, 9, 0.12);
  border-radius: 999px;
  font-size: 13px;
  color: rgb(var(--color-ink-mute));
  font-variant-numeric: tabular-nums;
  margin-left: auto;
}
.head-stat {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.head-stat strong {
  font-weight: 700;
  font-size: 14px;
  color: rgb(var(--color-ink));
}
.head-stat-label { font-size: 11px; letter-spacing: 0.5px; }
.head-stat-divider {
  width: 1px;
  height: 14px;
  background: rgba(180, 83, 9, 0.2);
}
.head-stat--up { color: #b45309; }
.head-stat--up strong { color: #92400e; }
.head-stat--trend-up { color: #15803d; }
.head-stat--trend-up strong { color: #166534; }
.head-stat--trend-down { color: #b91c1c; }
.head-stat--trend-down strong { color: #991b1b; }
.head-stat--trend-flat { color: rgb(var(--color-ink-mute)); }

.consensus-chip {
  padding: 3px 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(180, 83, 9, 0.08) 0%, rgba(180, 83, 9, 0.14) 100%);
  border: 1px solid rgba(180, 83, 9, 0.3);
  color: #92400e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
  cursor: help;
  margin-left: auto;
}

/* Variants grid: max 2-per-row — wider cards give the skills table room
   to breathe without forcing column truncation on 4-char hero names. */
.variants-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
  min-height: 160px;
}
@media (min-width: 768px) { .variants-grid { grid-template-columns: repeat(2, 1fr); } }

/* Proposals tab (unchanged grid). */
.proposal-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
}
@media (min-width: 768px)  { .proposal-grid { grid-template-columns: repeat(2, 1fr); } }
@media (min-width: 1280px) { .proposal-grid { grid-template-columns: repeat(3, 1fr); } }

.empty-state {
  text-align: center;
  color: rgb(var(--color-ink-mute));
  padding: 40px 0;
  font-size: 14px;
}
.empty-state--inline {
  grid-column: 1 / -1;
  padding: 60px 0;
}
</style>
