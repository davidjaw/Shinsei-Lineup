<template>
  <div class="flex-1 overflow-y-auto px-3 md:px-5 py-4">
    <div class="max-w-7xl">
      <!-- Toolbar -->
      <div class="flex items-center gap-3 mb-4 flex-wrap">
        <el-button type="primary" plain :icon="Plus" class="!rounded-sm" @click="onAddGroup">
          新增編組
        </el-button>
        <el-button plain :icon="Link" class="!rounded-sm" @click="onImportFromLink">
          由分享連結匯入…
        </el-button>
        <span class="text-xs text-ink-mute tabular-nums">
          共 <span class="font-bold text-ink">{{ groups.length }}</span> 個編組
        </span>
        <span class="text-xs text-ink-mute hidden sm:inline">·</span>
        <span class="text-xs text-ink-mute hidden sm:inline">
          目前顯示{{ modeLabel }}（兩邊獨立）
        </span>
        <span class="text-xs text-ink-mute hidden sm:inline">·</span>
        <span class="text-xs text-ink-mute hidden sm:inline">
          每組最多 {{ MAX_TEAMS_PER_GROUP }} 支隊伍
        </span>

        <el-tooltip
          content="編組僅暫存於本機。自由模式與庫存模式分開保存；如需備份請從配將模擬建立分享連結。"
          placement="top"
        >
          <span class="ml-auto inline-flex items-center gap-1 text-[11px] text-ink-mute cursor-help">
            <el-icon :size="12"><InfoFilled /></el-icon>本機暫存
          </span>
        </el-tooltip>
      </div>

      <!-- Group sections -->
      <div class="flex flex-col gap-6">
        <section
          v-for="(g, idx) in groups"
          :key="g.id"
          class="group-section"
          :class="{ 'group-section--active': idx === currentGroupIndex }"
        >
          <!-- Section header -->
          <header class="group-header">
            <span class="group-header__accent" aria-hidden="true"></span>

            <span class="group-header__index">{{ idx + 1 }}</span>

            <h2 class="font-brand text-xl font-bold text-ink truncate">
              {{ g.name }}
            </h2>

            <span v-if="idx === currentGroupIndex" class="active-badge">使用中</span>

            <div class="group-header__spacer"></div>

            <div class="group-header__stats">
              <span class="stat">
                <span class="stat__label">隊伍</span>
                <span class="stat__value">
                  {{ visibleTeams(g).length }}<span class="stat__sub">/{{ MAX_TEAMS_PER_GROUP }}</span>
                </span>
              </span>
              <span class="stat stat--cost">
                <span class="stat__label">Cost</span>
                <span class="stat__value">{{ groupCost(g) }}</span>
              </span>
            </div>

            <el-button
              v-if="idx !== currentGroupIndex"
              size="small"
              plain
              class="!rounded-sm !ml-1"
              @click="onSwitch(idx)"
            >切換到此</el-button>

            <el-dropdown trigger="click" @command="(cmd: string) => onMenu(cmd, idx)">
              <button type="button" class="icon-btn" title="更多操作">
                <el-icon :size="14"><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename" :icon="Edit">重新命名</el-dropdown-item>
                  <el-dropdown-item
                    command="delete"
                    :icon="Delete"
                    :disabled="groups.length <= 1"
                    divided
                  >
                    <span class="text-red-600">刪除編組</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </header>

          <!-- Roster grid: real teams render as the same TeamPreviewCard
               used everywhere else (share previews, proposals) so the level
               of detail — portraits, skills, breakthrough, bingxue, troop
               chips — matches what the user already knows. Placeholders
               only show when the group has NO real teams — a single empty
               row that prompts the first build. Once any team exists the
               grid is teams-only so the page reads as a roster, not as a
               "fill in the dots" form. -->
          <div class="thumb-grid">
            <TeamPreviewCard
              v-for="(team, ti) in visibleTeams(g)"
              :key="`t-${ti}`"
              :team="team"
              density="compact"
            />

            <button
              v-for="i in remainingSlots(g)"
              :key="`e-${i}`"
              type="button"
              class="empty-slot"
              :title="idx === currentGroupIndex ? '前往配將模擬建立新隊伍' : '切換到此編組以建立隊伍'"
              @click="onAddTeamHere(idx)"
            >
              <el-icon :size="22" class="empty-slot__icon"><Plus /></el-icon>
              <span class="empty-slot__label">建立第一支隊伍</span>
            </button>
          </div>
        </section>
      </div>
    </div>

    <!-- Rename dialog -->
    <el-dialog v-model="renameDialog.visible" title="重新命名編組" width="360px">
      <el-input
        v-model="renameDialog.draft"
        maxlength="20"
        show-word-limit
        placeholder="輸入新名稱"
        @keyup.enter="submitRename"
      />
      <template #footer>
        <el-button class="!rounded-sm" @click="renameDialog.visible = false">取消</el-button>
        <el-button type="primary" class="!rounded-sm" @click="submitRename">儲存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useDialogs } from '../composables/useDialogs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, MoreFilled, Edit, Delete, InfoFilled, Link } from '@element-plus/icons-vue'
import { useGroups } from '../composables/useGroups'
import { useInventory } from '../composables/useInventory'
import { MAX_TEAMS_PER_GROUP } from '../types/group'
import TeamPreviewCard from '../components/preview/TeamPreviewCard.vue'
import type { Group } from '../types/group'
import { isEmptyTeam, type Lineup } from '../composables/useLineups'

const router = useRouter()
const dialogs = useDialogs()
const {
  groups,
  currentGroupIndex,
  addGroup,
  removeGroup,
  renameGroup,
  setCurrentGroup,
} = useGroups()
const { catalogMode } = useInventory()
const modeLabel = computed(() =>
  catalogMode.value === 'inventory' ? '庫存模式' : '自由模式',
)

// Filter empty team slots from previews so a fresh group doesn't render
// three blank cards. Cached per group id so multiple template reads share
// one filter pass.
const visibleTeamsByGroup = computed<Map<string, Lineup[]>>(() => {
  const m = new Map<string, Lineup[]>()
  for (const g of groups.value) {
    m.set(g.id, g.teams.filter((t: Lineup) => !isEmptyTeam(t)))
  }
  return m
})
const visibleTeams = (g: Group): Lineup[] =>
  visibleTeamsByGroup.value.get(g.id) ?? []

// Placeholder count — only show empty slots when the group has NO real
// teams. Three placeholders fill one row at the 3-column desktop grid;
// narrower viewports wrap them but the intent (single empty row) still
// reads. Once any team exists the grid renders teams-only — adding more
// teams is done from the lineup builder, not from this view.
const PLACEHOLDER_ROW_COUNT = 3
const remainingSlots = (g: Group): number =>
  visibleTeams(g).length === 0 ? PLACEHOLDER_ROW_COUNT : 0

const groupCost = (g: Group): number =>
  g.teams.reduce((sum, t) => sum +
    (t.main.hero?.cost ?? 0) +
    (t.vice1.hero?.cost ?? 0) +
    (t.vice2.hero?.cost ?? 0), 0)

const onAddGroup = () => {
  const idx = addGroup()
  setCurrentGroup(idx)
  ElMessage.success(`已建立並切換到「${groups.value[idx].name}」`)
}

const onImportFromLink = () => {
  // Switch to the lineup builder first so the import dialog has the right
  // ambient state (currentGroup / lineups) and the user sees the result
  // immediately after confirming. The dialog itself is mounted there; we
  // just flip the route then ask the global dialogs registry to open it.
  void router.push({ name: 'lineup' }).then(() => {
    dialogs.open('import-from-link')
  })
}

const onSwitch = (idx: number) => {
  if (idx === currentGroupIndex.value) return
  setCurrentGroup(idx)
  ElMessage.success(`已切換到「${groups.value[idx].name}」`)
}

// Clicking an empty slot: if the target group is already active, jump
// straight to the builder; otherwise switch first so the builder opens on
// the right group. Either way the user lands ready to add a team.
const onAddTeamHere = (idx: number) => {
  if (idx !== currentGroupIndex.value) setCurrentGroup(idx)
  router.push({ name: 'lineup' })
}

// Rename dialog — single shared instance keyed by index. Submit is gated on
// non-empty draft; ESC / cancel discards.
const renameDialog = reactive({
  visible: false,
  idx: -1,
  draft: '',
})
const startRename = (idx: number) => {
  renameDialog.idx = idx
  renameDialog.draft = groups.value[idx]?.name ?? ''
  renameDialog.visible = true
}
const submitRename = () => {
  const name = renameDialog.draft.trim()
  if (!name) {
    ElMessage.warning('名稱不可為空')
    return
  }
  renameGroup(renameDialog.idx, name)
  renameDialog.visible = false
  ElMessage.success('編組已重新命名')
}

const onMenu = async (cmd: string, idx: number) => {
  if (cmd === 'rename') {
    startRename(idx)
    return
  }
  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(
        `確定要刪除「${groups.value[idx].name}」這個編組嗎？此操作無法復原。`,
        '刪除編組',
        { confirmButtonText: '刪除', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
    const ok = removeGroup(idx)
    if (ok) ElMessage.success('編組已刪除')
    else ElMessage.error('至少要保留一個編組')
  }
}
</script>

<style scoped>
.group-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Header strip — single horizontal line, no card chrome. The bottom border
   under the heading echoes the title-bar pattern used on TeamPreviewCard. */
.group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 4px 8px;
  border-bottom: 1px solid rgb(var(--color-divider));
  flex-wrap: wrap;
}
.group-header__accent {
  flex-shrink: 0;
  width: 4px;
  height: 22px;
  border-radius: 2px;
  background: rgb(var(--color-divider));
}
.group-section--active .group-header {
  border-bottom-color: rgb(var(--color-focus));
}
.group-section--active .group-header__accent {
  background: linear-gradient(180deg, #b45309 0%, rgb(var(--color-focus)) 100%);
}
.group-header__index {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: rgb(var(--color-ink-mute, 148 163 184));
  min-width: 14px;
  text-align: right;
}
.group-section--active .group-header__index { color: rgb(var(--color-focus)); }

.group-header__spacer { flex: 1 1 auto; min-width: 8px; }

.active-badge {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 2px;
  background: rgb(var(--color-highlight));
  color: rgb(var(--color-focus));
  border: 1px solid rgb(var(--color-focus) / 0.55);
  flex-shrink: 0;
  letter-spacing: 0.5px;
}

.group-header__stats {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  padding: 0 4px;
}
.stat {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-variant-numeric: tabular-nums;
}
.stat__label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.8px;
  color: rgb(var(--color-ink-mute, 148 163 184));
  text-transform: uppercase;
}
.stat__value {
  font-size: 17px;
  font-weight: 700;
  color: rgb(var(--color-ink));
}
.stat__sub {
  font-size: 12px;
  color: rgb(var(--color-ink-mute, 148 163 184));
  font-weight: 600;
}
.stat--cost .stat__value { color: #b45309; }

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: rgb(var(--color-ink-mute, 148 163 184));
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
}
.icon-btn:hover {
  background: #ffffff;
  border-color: rgb(var(--color-divider));
  color: rgb(var(--color-ink, 31 41 55));
}

/* The roster — responsive grid sized so a full TeamPreviewCard (compact)
   fits per cell without truncating portraits, skill names, or troop chips.
   Compact card needs ~340px to render its 3-col portrait + 3-col skill
   grid cleanly. minmax(360, 1fr) yields 3 cols at the 1280px container
   width, 2 cols on narrower laptops, 1 col on tablet/mobile. */
.thumb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 12px;
}

/* Empty slot — visually distinct from filled cards (dashed, muted). CSS
   grid auto-rows stretches each cell to the tallest in its row, so empty
   slots next to a filled TeamPreviewCard automatically match its height.
   min-height kicks in only for rows where every slot is empty, keeping the
   placeholder from collapsing into a thin strip. */
.empty-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 220px;
  background: transparent;
  border: 1.5px dashed rgb(var(--color-divider));
  border-radius: 12px;
  color: rgb(var(--color-ink-mute, 148 163 184));
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.empty-slot:hover {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
  color: rgb(var(--color-focus));
}
.empty-slot__icon { opacity: 0.6; }
.empty-slot:hover .empty-slot__icon { opacity: 1; }
.empty-slot__label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
}
</style>
