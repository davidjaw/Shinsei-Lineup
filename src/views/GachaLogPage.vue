<template>
  <div class="flex-1 overflow-y-auto p-4 md:p-6">
    <div class="max-w-7xl">
      <div v-if="!isLoggedIn" class="p-6 rounded-xl border border-dashed border-divider bg-white text-ink-soft">
        <p class="mb-3 text-sm">登入後抽卡紀錄會同步至雲端，可跨裝置存取與分享。</p>
        <el-button type="primary" @click="dialogs.open('auth')">登入 / 註冊</el-button>
      </div>

      <div v-else v-loading="isLoading" class="flex flex-col gap-3 min-h-[400px]">
          <!-- Inline create mode -->
          <div v-if="creatingBanner" class="flex items-center gap-2 pb-3 border-b border-divider">
            <span class="text-sm font-bold text-ink-mute flex-shrink-0">新增池</span>
            <el-input
              v-model="createDraft"
              size="default"
              maxlength="50"
              placeholder="例：S5 攻城武將池"
              class="!w-56"
              @keyup.enter="submitCreateBanner"
              @keyup.esc="cancelCreateBanner"
              autofocus
            />
            <el-button
              size="small"
              type="primary"
              :icon="Check"
              :loading="savingBanner"
              @click="submitCreateBanner"
            />
            <el-button size="small" :icon="Close" @click="cancelCreateBanner" />
          </div>

          <!-- Inline rename mode -->
          <div v-else-if="editingName" class="flex items-center gap-2 pb-3 border-b border-divider">
            <span class="text-sm font-bold text-ink-mute flex-shrink-0">重命名</span>
            <el-input
              v-model="nameDraft"
              size="default"
              maxlength="50"
              class="!w-56"
              @keyup.enter="submitRenameTitle"
              @keyup.esc="cancelRenameTitle"
              autofocus
            />
            <el-button size="small" type="primary" :icon="Check" @click="submitRenameTitle" />
            <el-button size="small" :icon="Close" @click="cancelRenameTitle" />
          </div>

          <!-- Banner switcher pill + actions -->
          <div v-else-if="banners.length > 0 && !editingPool" class="flex items-center gap-2 pb-3 border-b border-divider flex-wrap">
            <el-dropdown trigger="click" @command="onBannerCommand" placement="bottom-start">
              <button class="banner-pill" type="button">
                <el-icon :size="13" class="opacity-70"><MagicStick /></el-icon>
                <span class="font-bold text-ink">池</span>
                <span class="font-bold text-focus truncate max-w-[180px]">
                  {{ currentBanner?.name || '尚無池' }}
                </span>
                <el-icon :size="12" class="opacity-60"><ArrowDown /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu class="min-w-[240px]">
                  <el-dropdown-item
                    v-for="b in banners"
                    :key="b.id"
                    :command="`switch:${b.id}`"
                    :class="{ '!font-bold !text-focus': b.id === currentBannerId }"
                  >
                    <el-icon class="mr-1" :class="b.id === currentBannerId ? 'text-amber-500' : 'opacity-60'">
                      <component :is="b.id === currentBannerId ? StarFilled : MagicStick" />
                    </el-icon>
                    <span class="flex-1 truncate mr-2">{{ b.name }}</span>
                    <span class="text-[11px] text-ink-mute tabular-nums">{{ b.hero_pool.length }}武</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="create" divided>
                    <el-icon class="mr-1"><Plus /></el-icon> 新增池…
                  </el-dropdown-item>
                  <el-dropdown-item v-if="currentBanner" command="rename">
                    <el-icon class="mr-1"><Edit /></el-icon> 重命名
                  </el-dropdown-item>
                  <el-dropdown-item v-if="currentBanner" command="delete">
                    <el-icon class="mr-1 text-red-500"><Delete /></el-icon>
                    <span class="text-red-500">刪除此池</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>

            <div class="ml-auto flex items-center gap-2">
              <el-button plain @click="startEditPool" class="!rounded-sm action-btn">
                <el-icon><Edit /></el-icon>
                <span class="ml-1 hidden sm:inline">編輯池內武將</span>
              </el-button>
              <el-button
                type="primary"
                plain
                :disabled="currentDraws.length === 0"
                @click="onShare"
                class="!rounded-sm action-btn"
              >
                <el-icon><Share /></el-icon>
                <span class="ml-1 hidden sm:inline">分享</span>
              </el-button>
            </div>
          </div>

          <!-- Empty banners state -->
          <div
            v-if="banners.length === 0 && !creatingBanner"
            class="flex flex-col items-center justify-center py-16 text-center"
          >
            <p class="text-sm text-ink-mute mb-3">還沒有任何抽卡池</p>
            <el-button type="primary" :icon="Plus" @click="startCreateBanner">建立第一個池</el-button>
          </div>

          <template v-else-if="currentBanner && !editingPool">
            <!-- Stats bar: pity + counts + actions -->
            <div class="bg-gradient-to-r from-yellow-50 to-orange-50 border border-yellow-200 rounded-lg p-3">
              <div class="flex items-center gap-3 flex-wrap">
                <div class="flex items-baseline gap-1.5 flex-shrink-0">
                  <span class="text-xs text-orange-700 font-bold">距上次稀有</span>
                  <span class="text-xl md:text-2xl font-bold tabular-nums text-orange-600">{{ pityCount }}</span>
                  <span class="text-xs text-gray-500">/ 6 抽</span>
                </div>
                <div class="flex gap-3 text-xs text-gray-700 flex-shrink-0 ml-auto">
                  <span>總計 <b class="text-gray-900">{{ totalDraws }}</b></span>
                  <span>稀有抽數 <b class="text-yellow-600">★{{ markedCount }}</b></span>
                  <span>池內 <b class="text-gray-900">{{ currentBanner.hero_pool.length }}</b></span>
                </div>
              </div>
              <!-- Pity progress: 6 segments. Slot 6 = guaranteed-rare slot. -->
              <div class="mt-2">
                <div class="flex gap-1">
                  <div
                    v-for="i in 6"
                    :key="i"
                    class="flex-1 h-3 rounded-sm transition-colors"
                    :class="segmentClass(i)"
                  ></div>
                </div>
                <div
                  v-if="pityCount > 5"
                  class="mt-1.5 text-[11px] md:text-xs text-amber-700 flex items-center gap-1"
                >
                  <span>💡</span>
                  依保底機制，這 6 抽通常會出 1 個較好的；右鍵可標記為稀有以重置計數
                </div>
              </div>
            </div>

            <!-- Tabs: picker / log+stats merged -->
            <el-tabs v-model="activeTab" class="gacha-tabs">
              <el-tab-pane label="快速登錄" name="picker" lazy>
                <div class="flex flex-col gap-2">
                  <div
                    v-if="currentDraws.length > 0"
                    class="flex-shrink-0 border-b border-gray-200 pb-2"
                  >
                    <div class="flex items-center gap-2 mb-1.5">
                      <span class="text-xs text-gray-500 font-bold">本池紀錄</span>
                      <span class="text-xs text-gray-400">{{ currentDraws.length }} 筆 · 最新在左</span>
                      <span class="text-xs text-gray-400 ml-auto">右鍵或長按開啟動作選單</span>
                    </div>
                    <GachaLogList
                      :draws="pickerDraws"
                      :hero-by-jp="heroByJp"
                      flat
                      horizontal
                      :rare-set="currentRareSet"
                      @toggle-rare="onToggleHeroRare"
                      @delete="onDeleteDraw"
                    />
                  </div>
                  <div class="picker-area">
                    <GachaHeroPicker
                      :heroes="heroes"
                      :pool="currentBanner.hero_pool"
                      :marked-per-hero="markedPerHero"
                      @select="onSelectHero"
                      @edit-pool="startEditPool"
                    />
                  </div>
                </div>
              </el-tab-pane>
              <el-tab-pane :label="`紀錄與統計 (${currentDraws.length})`" name="log" lazy>
                <div class="flex flex-col">
                  <div v-if="currentDraws.length > 0" class="flex flex-col gap-2 mb-3">
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <div class="bg-gray-50 rounded p-2 text-center">
                        <div class="text-xs text-gray-500">總抽卡</div>
                        <div class="text-base md:text-lg font-bold tabular-nums">{{ totalDraws }}</div>
                      </div>
                      <div class="bg-gray-50 rounded p-2 text-center">
                        <div class="text-xs text-gray-500">稀有抽數</div>
                        <div class="text-base md:text-lg font-bold tabular-nums text-yellow-600">★{{ markedCount }}</div>
                      </div>
                      <div class="bg-gray-50 rounded p-2 text-center">
                        <div class="text-xs text-gray-500">稀有中位數</div>
                        <div class="text-base md:text-lg font-bold tabular-nums">{{ medianGap ?? '—' }}</div>
                      </div>
                      <div class="bg-gray-50 rounded p-2 text-center">
                        <div class="text-xs text-gray-500">距上次稀有</div>
                        <div class="text-base md:text-lg font-bold tabular-nums text-orange-600">{{ pityCount }}</div>
                      </div>
                    </div>
                    <details class="bg-gray-50 rounded p-2">
                      <summary class="text-xs font-bold text-gray-700 cursor-pointer">出現頻率 Top 10</summary>
                      <div class="space-y-1 mt-2">
                        <div
                          v-for="(row, i) in topHeroes"
                          :key="row.jp"
                          class="flex items-center gap-2 text-xs px-1.5 py-0.5 rounded transition-colors"
                          :class="markedPerHero.get(row.jp)
                            ? 'bg-yellow-50 ring-1 ring-yellow-200'
                            : ''"
                        >
                          <span class="text-[11px] text-gray-400 w-4 text-right">{{ i + 1 }}</span>
                          <span
                            class="w-20 md:w-32 truncate font-medium"
                            :class="markedPerHero.get(row.jp) ? 'text-yellow-800' : ''"
                          >{{ heroByJp.get(row.jp)?.name || row.jp }}</span>
                          <div class="flex-1 bg-white rounded h-2 overflow-hidden border border-gray-100">
                            <div
                              class="h-full"
                              :class="markedPerHero.get(row.jp) ? 'bg-yellow-400' : 'bg-blue-400'"
                              :style="{ width: ((row.count / topHeroes[0].count) * 100) + '%' }"
                            ></div>
                          </div>
                          <span class="tabular-nums w-8 text-right">{{ row.count }}</span>
                          <span v-if="markedPerHero.get(row.jp)" class="text-yellow-500 text-sm leading-none">★</span>
                        </div>
                      </div>
                    </details>
                  </div>

                  <div class="flex items-center gap-2 mb-2 flex-shrink-0">
                    <span class="text-xs text-gray-400 ml-auto">右鍵或長按開啟動作選單</span>
                  </div>
                  <div class="px-0.5">
                    <GachaLogList
                      :draws="currentDraws"
                      :hero-by-jp="heroByJp"
                      :rare-set="currentRareSet"
                      @toggle-rare="onToggleHeroRare"
                      @delete="onDeleteDraw"
                    />
                  </div>
                </div>
              </el-tab-pane>
            </el-tabs>
          </template>

          <!-- Pool edit mode -->
          <template v-else-if="currentBanner && editingPool">
            <div class="flex items-center gap-2 mb-2 flex-shrink-0">
              <span class="text-sm font-bold text-gray-700">編輯池內武將</span>
              <span class="text-[11px] text-gray-400">已選 {{ poolDraftCht.length }} 位</span>
              <div class="ml-auto flex gap-1">
                <el-button size="small" @click="cancelEditPool">取消</el-button>
                <el-button
                  size="small"
                  type="primary"
                  :loading="savingPool"
                  :icon="Check"
                  @click="submitEditPool"
                >完成</el-button>
              </div>
            </div>
            <div class="md:border md:border-gray-200 md:rounded md:p-2">
              <GachaPoolEditor
                :heroes="heroes"
                v-model="poolDraftCht"
              />
            </div>
          </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu,
  ElInput, ElMessage, ElMessageBox, ElTabPane, ElTabs,
} from 'element-plus'
import {
  ArrowDown, Check, Close, Delete, Edit,
  MagicStick, Plus, Share, StarFilled,
} from '@element-plus/icons-vue'
import { useData, type Hero } from '../composables/useData'
import { computeMedianGap, computeTopHeroes, useGachaLog } from '../composables/useGachaLog'
import { useAuth } from '../composables/useAuth'
import { useDialogs } from '../composables/useDialogs'
import { createShare } from '../lib/share'
import { getSession } from '../lib/auth'
import GachaHeroPicker from '../components/GachaHeroPicker.vue'
import GachaLogList from '../components/GachaLogList.vue'
import GachaPoolEditor from '../components/GachaPoolEditor.vue'

const { isLoggedIn } = useAuth()
const dialogs = useDialogs()
const { heroes } = useData()
const {
  banners,
  currentBanner,
  currentBannerId,
  currentRareSet,
  isLoading,
  currentDraws,
  pityCount,
  totalDraws,
  markedCount,
  drawsPerHero,
  markedPerHero,
  loadBanners,
  loadDraws,
  selectBanner,
  createBanner,
  renameBanner,
  updateBannerPool,
  deleteBanner,
  logDraw,
  toggleHeroRare,
  deleteDraw,
} = useGachaLog()

const activeTab = ref<'picker' | 'log'>('picker')

const editingName = ref(false)
const nameDraft = ref('')
const startRenameTitle = (): void => {
  if (!currentBanner.value) return
  nameDraft.value = currentBanner.value.name
  editingName.value = true
}
const cancelRenameTitle = (): void => {
  editingName.value = false
}
const submitRenameTitle = async (): Promise<void> => {
  if (!currentBanner.value) return
  const name = nameDraft.value.trim()
  if (!name || name === currentBanner.value.name) {
    editingName.value = false
    return
  }
  try {
    await renameBanner(currentBanner.value.id, name)
    editingName.value = false
    ElMessage.success('已重命名')
  } catch (e) {
    ElMessage.error(`重命名失敗：${(e as Error).message}`)
  }
}

const creatingBanner = ref(false)
const createDraft = ref('')
const savingBanner = ref(false)

const startCreateBanner = (): void => {
  createDraft.value = ''
  creatingBanner.value = true
}
const cancelCreateBanner = (): void => {
  creatingBanner.value = false
  createDraft.value = ''
}
const submitCreateBanner = async (): Promise<void> => {
  const name = createDraft.value.trim()
  if (!name) return
  savingBanner.value = true
  try {
    await createBanner(name)
    creatingBanner.value = false
    createDraft.value = ''
    // Newly created banners have empty hero_pool — drop into pool edit so the
    // user can configure who's in the banner without an extra navigation step.
    startEditPool()
  } catch (e) {
    ElMessage.error(`建立失敗：${(e as Error).message}`)
  } finally {
    savingBanner.value = false
  }
}

const onBannerCommand = async (cmd: string): Promise<void> => {
  if (cmd === 'create') {
    startCreateBanner()
  } else if (cmd === 'rename') {
    startRenameTitle()
  } else if (cmd === 'delete') {
    await onDeleteBanner()
  } else if (cmd.startsWith('switch:')) {
    const id = cmd.slice(7)
    if (id === currentBannerId.value) return
    try {
      await selectBanner(id)
    } catch (e) {
      ElMessage.error(`切換失敗：${(e as Error).message}`)
    }
  }
}

const onDeleteBanner = async (): Promise<void> => {
  const banner = currentBanner.value
  if (!banner) return
  try {
    await ElMessageBox.confirm(
      `刪除「${banner.name}」與其全部紀錄？無法復原。`,
      '確認刪除',
      {
        confirmButtonText: '刪除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  try {
    await deleteBanner(banner.id)
    ElMessage.success('已刪除')
  } catch (e) {
    ElMessage.error(`刪除失敗：${(e as Error).message}`)
  }
}

const heroByJp = computed<Map<string, Hero>>(() => {
  const m = new Map<string, Hero>()
  for (const h of heroes.value) {
    const key = h.name_jp || h.name
    if (key) m.set(key, h)
  }
  return m
})

const heroByCht = computed<Map<string, Hero>>(() => {
  const m = new Map<string, Hero>()
  for (const h of heroes.value) m.set(h.name, h)
  return m
})

const segmentClass = (slot: number): string => {
  if (slot > pityCount.value) return 'bg-white border border-yellow-200'
  if (slot === 6) return 'bg-amber-600'
  if (slot >= 4) return 'bg-orange-500'
  return 'bg-yellow-400'
}

const medianGap = computed<number | null>(() => {
  const rare = currentRareSet.value
  const positions: number[] = []
  currentDraws.value.forEach((d, i) => {
    if (rare.has(d.hero_jp)) positions.push(i)
  })
  return computeMedianGap(positions)
})

const topHeroes = computed<{ jp: string; count: number }[]>(() =>
  computeTopHeroes(drawsPerHero.value),
)

const PICKER_STRIP_LIMIT = 50
const pickerDraws = computed(() => currentDraws.value.slice(0, PICKER_STRIP_LIMIT))

const editingPool = ref(false)
const poolDraftCht = ref<string[]>([])
const savingPool = ref(false)

const startEditPool = (): void => {
  if (!currentBanner.value) return
  const chts: string[] = []
  for (const jp of currentBanner.value.hero_pool) {
    const h = heroByJp.value.get(jp)
    if (h && Number(h.rarity) === 5) chts.push(h.name)
  }
  poolDraftCht.value = chts
  editingPool.value = true
}

const cancelEditPool = (): void => {
  editingPool.value = false
  poolDraftCht.value = []
}

const submitEditPool = async (): Promise<void> => {
  if (!currentBanner.value) return
  const jpList: string[] = []
  for (const cht of poolDraftCht.value) {
    const h = heroByCht.value.get(cht)
    if (!h) continue
    if (Number(h.rarity) !== 5) continue
    jpList.push(h.name_jp || h.name)
  }
  savingPool.value = true
  try {
    await updateBannerPool(currentBanner.value.id, jpList)
    editingPool.value = false
    poolDraftCht.value = []
    ElMessage.success('池內武將已更新')
  } catch (e) {
    ElMessage.error(`儲存失敗：${(e as Error).message}`)
  } finally {
    savingPool.value = false
  }
}

// As a page (vs. a dialog), banner state must be hydrated on mount instead
// of on dialog-visible. The composable resets state on signout, so re-entering
// the route after a fresh login still triggers a clean load.
const hydrate = async (): Promise<void> => {
  if (!isLoggedIn.value) return
  try {
    await loadBanners()
    if (currentBannerId.value) await loadDraws(currentBannerId.value)
  } catch (e) {
    ElMessage.error(`載入失敗：${(e as Error).message}`)
  }
}

onMounted(hydrate)
watch(isLoggedIn, (now) => { if (now) void hydrate() })

const onSelectHero = async (hero: Hero): Promise<void> => {
  try {
    await logDraw(hero)
  } catch (e) {
    ElMessage.error(`登錄失敗：${(e as Error).message}`)
  }
}

const onToggleHeroRare = async (heroJp: string): Promise<void> => {
  try {
    await toggleHeroRare(heroJp)
  } catch (e) {
    ElMessage.error(`標記失敗：${(e as Error).message}`)
  }
}

const onDeleteDraw = async (drawId: number): Promise<void> => {
  try {
    await deleteDraw(drawId)
    ElMessage.success('已刪除')
  } catch (e) {
    ElMessage.error(`刪除失敗：${(e as Error).message}`)
  }
}

const onShare = async (): Promise<void> => {
  if (!currentBanner.value) return
  const blob = {
    v: 3,
    kind: 'gacha_log',
    banner: {
      name: currentBanner.value.name,
      rare_heroes: currentBanner.value.rare_heroes,
    },
    draws: currentDraws.value.map(d => ({
      hero_jp: d.hero_jp,
      rarity: d.rarity,
      drawn_at: d.drawn_at,
    })),
    meta: {
      snapshot_at: new Date().toISOString(),
      display_name: getSession()?.user.display_name ?? null,
    },
  }
  try {
    const slug = await createShare(blob, { kind: 'gacha_log' })
    const url = `${location.origin}${location.pathname}#s/${slug}`
    await navigator.clipboard.writeText(url).catch(() => undefined)
    ElMessage.success('已建立分享連結並複製到剪貼簿')
  } catch (e) {
    ElMessage.error(`分享失敗：${(e as Error).message}`)
  }
}
</script>

<style scoped>
.gacha-tabs :deep(.el-tabs__nav-wrap)::after {
  height: 1px;
}
.picker-area {
  /* Reserve enough room for the hero-picker grid; the dialog version
     relied on `flex-1 + h-full` from a fixed-height parent, but the page
     just lets the picker pick its own intrinsic height. */
  min-height: 360px;
}
.banner-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border-radius: 2px;
  background: rgb(var(--color-surface-muted));
  border: 1px solid rgb(var(--color-divider));
  color: #1F2937;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
  line-height: 1;
  box-sizing: border-box;
}
.banner-pill:hover {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
}
.banner-pill:focus-visible {
  outline: 2px solid rgb(var(--color-focus));
  outline-offset: 2px;
}
.action-btn {
  height: 32px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
</style>
