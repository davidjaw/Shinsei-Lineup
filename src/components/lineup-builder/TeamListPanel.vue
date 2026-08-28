<template>
  <aside class="hidden md:flex flex-col w-[200px] flex-shrink-0 border-r border-divider bg-white text-ink h-full overflow-hidden">
    <!-- Group selector lives in LineupHeader (top bar). Sidebar is just the
         team list for the active group. -->
    <div class="flex-1 min-h-0 overflow-y-auto pt-2">
      <div
        v-for="(team, idx) in lineups"
        :key="idx"
        role="button"
        tabindex="0"
        class="group relative w-full flex items-center justify-between pl-0 pr-3 py-2 transition-colors text-left border-l-2 cursor-pointer"
        :class="currentTeamIndex === idx
          ? 'bg-highlight border-focus'
          : 'border-transparent hover:bg-highlight'"
        @click="$emit('select', idx)"
        @keydown.enter="$emit('select', idx)"
        @keydown.space.prevent="$emit('select', idx)"
      >
        <div class="flex items-center gap-1.5 min-w-0">
          <span class="text-[11px] text-ink-mute w-4 text-right">{{ idx + 1 }}</span>
          <span class="text-xs truncate">{{ team.name }}</span>
        </div>
        <div class="flex items-center gap-1.5 flex-shrink-0">
          <span
            class="text-[11px] tabular-nums"
            :class="teamCost(team) > 20 ? 'text-red-500' : 'text-ink-mute'"
          >{{ teamCost(team) }}/20</span>
          <span
            v-if="hasUnsavedChanges(idx)"
            class="w-1.5 h-1.5 rounded-full bg-focus"
            aria-label="unsaved"
          />
          <!-- Empty team → instant delete. Non-empty → popconfirm. -->
          <span
            v-if="isEmptyTeam(team)"
            class="row-action opacity-0 group-hover:opacity-100 focus-within:opacity-100"
            @click.stop="$emit('remove-team', idx)"
            @keydown.enter.stop="$emit('remove-team', idx)"
            @keydown.space.stop.prevent="$emit('remove-team', idx)"
            role="button"
            tabindex="0"
            :aria-label="`刪除 ${team.name}`"
          >
            <el-icon :size="13"><Delete /></el-icon>
          </span>
          <el-popconfirm
            v-else
            :title="`刪除「${team.name}」？無法復原`"
            confirm-button-text="刪除"
            cancel-button-text="取消"
            confirm-button-type="danger"
            :width="220"
            @confirm="$emit('remove-team', idx)"
          >
            <template #reference>
              <span
                class="row-action opacity-0 group-hover:opacity-100 focus-within:opacity-100"
                @click.stop
                role="button"
                tabindex="0"
                :aria-label="`刪除 ${team.name}`"
              >
                <el-icon :size="13"><Delete /></el-icon>
              </span>
            </template>
          </el-popconfirm>
        </div>
      </div>

      <button
        v-if="lineups.length < MAX_TEAMS_PER_GROUP"
        type="button"
        class="w-full pl-0 pr-3 py-2 mt-1 text-left text-xs text-ink-mute hover:text-ink hover:bg-surface-muted transition-colors flex items-center gap-1 border-l-2 border-transparent"
        @click="$emit('add-team')"
      >
        <span class="w-4 text-right">
          <el-icon :size="12"><Plus /></el-icon>
        </span>
        <span>新增配將</span>
      </button>
    </div>

    <div class="border-t border-divider px-3 py-3 flex flex-col gap-1.5">
      <button class="action-row" @click="$emit('compact')">
        <el-icon :size="14"><FullScreen /></el-icon>
        <span>截圖模式</span>
      </button>
      <button class="action-row" @click="$emit('share')">
        <el-icon :size="14"><Share /></el-icon>
        <span>分享</span>
      </button>
      <button class="action-row" @click="$emit('save-as-proposal')">
        <el-icon :size="14"><Document /></el-icon>
        <span>另存為精選隊伍</span>
      </button>
      <button class="action-row" @click="$emit('export-to-group')">
        <el-icon :size="14"><Position /></el-icon>
        <span>導出到其他編組</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Share, Document, Plus, Delete, Position, FullScreen } from '@element-plus/icons-vue'
import { type Lineup, isEmptyTeam, computeTeamCost } from '../../composables/useLineups'
import { MAX_TEAMS_PER_GROUP } from '../../types/group'

defineProps<{
  lineups: Lineup[]
  currentTeamIndex: number
}>()

defineEmits<{
  (e: 'select', idx: number): void
  (e: 'add-team'): void
  (e: 'share'): void
  (e: 'save-as-proposal'): void
  (e: 'export-to-group'): void
  (e: 'remove-team', idx: number): void
  (e: 'compact'): void
}>()

const teamCost = computeTeamCost

// Stub — needs a per-team baseline snapshot to diff against. Lands with
// the proposal-save / share-blob persistence work in a later phase.
const hasUnsavedChanges = (_idx: number): boolean => false
</script>

<style scoped>
.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: #475569;
  background: transparent;
  border: 1px solid transparent;
  transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
  text-align: left;
  cursor: pointer;
}
.action-row:hover {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
  color: #1F2937;
}

.row-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: #94a3b8;
  cursor: pointer;
  transition: color 0.12s ease, background 0.12s ease, opacity 0.12s ease;
}
.row-action:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
}
</style>
