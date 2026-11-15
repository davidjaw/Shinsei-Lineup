<template>
  <div class="flex items-center flex-shrink-0" :class="{ 'w-full': wide }" data-testid="game-season-control">
    <el-dropdown trigger="click" placement="bottom-start" :class="{ 'w-full': wide }" @command="onCommand">
      <button
        class="season-pill"
        :class="{ 'has-misfits': misfits.length > 0, 'is-wide': wide }"
        type="button"
        :title="misfits.length ? `賽季 ${gameSeason}：目前編組有 ${misfits.length} 項 ${gameSeason} 沒有的武將或戰法` : '選擇賽季：選將與選戰法只列出這一季可用的'"
        data-testid="game-season-pill"
      >
        <span class="font-bold text-ink" :class="wide ? '' : 'hidden 2xl:inline'">賽季</span>
        <span class="font-bold text-focus" data-testid="game-season-value">{{ gameSeason }}</span>
        <span v-if="misfits.length" class="season-badge" data-testid="game-season-badge">{{ misfits.length }}</span>
        <span v-if="wide" class="flex-1" />
        <el-icon :size="12" class="opacity-60"><ArrowDown /></el-icon>
      </button>
      <template #dropdown>
        <el-dropdown-menu class="min-w-[180px]">
          <el-dropdown-item
            v-for="s in gameSeasons"
            :key="s"
            :command="s"
            :class="{ '!font-bold !text-focus': s === gameSeason }"
            :data-testid="`game-season-option-${s}`"
          >{{ s }}</el-dropdown-item>
          <el-dropdown-item
            v-if="clearable && misfits.length"
            :command="CLEAR"
            divided
            class="!text-red-600 !font-bold"
            data-testid="game-season-clear"
          >
            <el-icon class="mr-1"><Close /></el-icon> 移除非本賽季（{{ misfits.length }} 項）
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <el-dialog v-model="confirmingClear" :title="`移除非 ${gameSeason} 的武將與戰法`" width="420px" align-center append-to-body>
      <div class="text-sm text-ink-soft" data-testid="game-season-clear-dialog">
        <p>會從編組「{{ currentGroup.name }}」清掉下列 {{ misfits.length }} 項。武將會連同那一格的戰法、突破與兵學一起清掉。</p>
        <p class="mt-2 font-bold text-ink" data-testid="game-season-clear-names">{{ namesOf(misfits) }}</p>
      </div>
      <template #footer>
        <el-button @click="confirmingClear = false">取消</el-button>
        <el-button type="danger" data-testid="game-season-clear-ok" @click="clearNow">移除</el-button>
      </template>
    </el-dialog>

    <el-dialog :model-value="asking !== null" :title="`切換到 ${asking?.season ?? ''}`" width="440px" align-center append-to-body @update:model-value="asking = null">
      <div class="text-sm text-ink-soft" data-testid="game-season-switch-dialog">
        <p>目前編組「{{ currentGroup.name }}」有 {{ asking?.misfits.length ?? 0 }} 項 {{ asking?.season }} 沒有。保留的會留在原位並加上標記。</p>
        <p class="mt-2 font-bold text-ink" data-testid="game-season-switch-names">{{ namesOf(asking?.misfits ?? []) }}</p>
      </div>
      <template #footer>
        <el-button data-testid="game-season-switch-cancel" @click="asking = null">取消</el-button>
        <el-button data-testid="game-season-switch-keep" @click="answer(false)">保留並切換</el-button>
        <el-button type="danger" data-testid="game-season-switch-clear" @click="answer(true)">移除並切換</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// The lineup page's game season beside the group: a pill with the season and, while the active group holds something
// the season does not offer, how many; its menu picks a season and offers 移除非本賽季. Switching to a season that
// would leave something out asks first (remove and switch, keep and switch, or cancel); kept items stay where they
// are, marked. Clearing lists what goes before it goes. State: ../../composables/useGameSeason.ts.
import { ref } from 'vue'
import { ArrowDown, Close } from '@element-plus/icons-vue'
import { useGameSeason } from '../../composables/useGameSeason'
import { useGroups } from '../../composables/useGroups'
import { gameSeasonMisfitNames, type GameSeasonMisfit } from '../../lib/gameSeasonMisfits'

// `wide`: the phone drawer's full-width row, labelled; otherwise the header's pill, labelled only where there is room.
withDefaults(defineProps<{ clearable?: boolean; wide?: boolean }>(), { clearable: true, wide: false })

const { gameSeason, gameSeasons, misfits, misfitsUnder, clearMisfits, switchGameSeason } = useGameSeason()
const { currentGroup } = useGroups()
const namesOf = (list: readonly GameSeasonMisfit[]): string => gameSeasonMisfitNames(list).join('、')

const asking = ref<{ season: string; misfits: GameSeasonMisfit[] } | null>(null)
function pick(season: string): void {
  if (season === gameSeason.value) return
  const left = misfitsUnder(season)
  if (left.length) asking.value = { season, misfits: left }
  else switchGameSeason(season, false)
}
function answer(clearing: boolean): void {
  if (asking.value) switchGameSeason(asking.value.season, clearing)
  asking.value = null
}

const confirmingClear = ref(false)
function clearNow(): void {
  clearMisfits()
  confirmingClear.value = false
}

/** The menu's command: a season to switch to, or CLEAR. */
const CLEAR = '__clear__'
function onCommand(command: string): void {
  if (command === CLEAR) confirmingClear.value = true
  else pick(command)
}
</script>

<style scoped>
.season-pill {
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
.season-pill:hover {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
}
.season-pill.is-wide {
  width: 100%;
  height: 34px;
}
.season-pill.has-misfits {
  border-color: #fca5a5;
}
.season-pill:focus-visible {
  outline: 2px solid rgb(var(--color-focus));
  outline-offset: 2px;
}
.season-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #dc2626;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
}
</style>
