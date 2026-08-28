<template>
  <el-dialog
    v-model="visible"
    title="偵測到尚未同步的編組變更"
    width="600px"
    :close-on-click-modal="false"
    :show-close="false"
    align-center
  >
    <template v-if="ctx">
      <p class="text-sm text-ink-soft mb-4 leading-relaxed">
        這台裝置上有尚未同步的編組，與此帳號上次保存的編組不同。請選擇要如何整合：
      </p>

      <!-- Local vs cloud side cards. Each side has a 預覽 button that opens
           a sub-dialog rendering full TeamPreviewCards via the share hydrator,
           so the user can verify exactly what they're keeping/discarding. -->
      <div class="grid grid-cols-2 gap-3 mb-5">
        <section class="side-card">
          <header class="side-card__head">
            <span class="side-card__tag">此裝置</span>
            <span class="side-card__count tabular-nums">
              <strong>{{ localCount }}</strong> 編組
            </span>
          </header>
          <ul class="side-card__list">
            <li v-for="g in localPreviewList" :key="g.id ?? g.name" class="truncate">
              {{ g.name }} <span class="text-ink-mute">· {{ nonEmptyCount(g.teams) }} 隊</span>
            </li>
            <li v-if="localOverflow > 0" class="text-ink-mute italic">
              … 以及其他 {{ localOverflow }} 個
            </li>
          </ul>
          <el-button
            size="small"
            plain
            :icon="View"
            class="!rounded-sm side-card__preview"
            @click="openLocalPreview"
          >預覽此裝置編組</el-button>
        </section>

        <section class="side-card">
          <header class="side-card__head">
            <span class="side-card__tag side-card__tag--cloud">帳號保存</span>
            <span class="side-card__count tabular-nums">
              <strong>{{ cloudCount }}</strong> 編組
            </span>
          </header>
          <ul class="side-card__list">
            <li v-for="r in cloudPreviewList" :key="r.id" class="truncate">
              {{ r.name }} <span class="text-ink-mute">· {{ nonEmptyCount(r.teams) }} 隊</span>
            </li>
            <li v-if="cloudOverflow > 0" class="text-ink-mute italic">
              … 以及其他 {{ cloudOverflow }} 個
            </li>
          </ul>
          <el-button
            size="small"
            plain
            :icon="View"
            class="!rounded-sm side-card__preview"
            @click="openCloudPreview"
          >預覽帳號保存的編組</el-button>
        </section>
      </div>

      <!-- Option cards. Element Plus' <el-radio> puts the bullet beside the
           label's first line, which mis-aligns multi-line content. Rendering
           each option as a <label>-wrapped card with the radio + content
           in flex restores top-aligned grouping and is also easier to click. -->
      <div class="flex flex-col gap-2 mb-1">
        <label
          v-for="opt in OPTIONS"
          :key="opt.value"
          class="option-card"
          :class="{ 'option-card--active': choice === opt.value }"
        >
          <input
            type="radio"
            class="option-card__radio"
            :value="opt.value"
            v-model="choice"
          />
          <div class="option-card__content">
            <span class="option-card__title">{{ opt.label }}</span>
            <span class="option-card__hint">{{ opt.hint }}</span>
          </div>
        </label>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <el-button class="!rounded-sm" :disabled="busy" @click="onCancel">稍後再決定</el-button>
        <el-button
          type="primary"
          class="!rounded-sm"
          :loading="busy"
          @click="onConfirm"
        >確認</el-button>
      </div>
    </template>
  </el-dialog>

  <!-- Preview sub-dialogs. append-to-body so they layer above the merge
       dialog cleanly; close-on-click-modal so dismissing them doesn't
       cascade into closing the merge dialog. -->
  <el-dialog
    v-model="localPreviewOpen"
    title="此裝置編組預覽"
    width="720px"
    append-to-body
    align-center
  >
    <div v-if="localGroupsHydrated.length === 0" class="text-center text-ink-mute py-6 text-sm">
      此裝置沒有可預覽的編組。
    </div>
    <div v-else class="flex flex-col gap-4 max-h-[70vh] overflow-y-auto pr-1">
      <GroupPreviewCard
        v-for="g in localGroupsHydrated"
        :key="g.name"
        :group="g"
        density="compact"
        :show-watermark="false"
      />
    </div>
  </el-dialog>

  <el-dialog
    v-model="cloudPreviewOpen"
    title="帳號保存的編組預覽"
    width="720px"
    append-to-body
    align-center
  >
    <div v-if="cloudGroupsHydrated.length === 0" class="text-center text-ink-mute py-6 text-sm">
      此帳號之前沒有保存的編組。
    </div>
    <div v-else class="flex flex-col gap-4 max-h-[70vh] overflow-y-auto pr-1">
      <GroupPreviewCard
        v-for="g in cloudGroupsHydrated"
        :key="g.name"
        :group="g"
        density="compact"
        :show-watermark="false"
      />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { View } from '@element-plus/icons-vue'
import { useGroupPersistence } from '../../composables/useGroupPersistence'
import { useData } from '../../composables/useData'
import { hydrateShare } from '../preview/hydrateShare'
import GroupPreviewCard from '../preview/GroupPreviewCard.vue'
import { isEmptyTeam, type Lineup } from '../../composables/useLineups'
import { isEmptyShareableLineup, shareableGroupsInBlob } from '../../lib/lineupSerialize'
import type { ShareableData, ShareableGroup, ShareableLineup } from '../../constants/gameData'

const APPEND_MAX_TOTAL = 20  // mirrors useGroupPersistence.resolveMergeAppend

const OPTIONS = [
  {
    value: 'append',
    label: '兩邊都保留（合併）',
    hint: `此裝置上的編組保持不動，帳號之前保存的編組接在後面（自由／庫存各最多 ${APPEND_MAX_TOTAL} 個）。`,
  },
  {
    value: 'keep-cloud',
    label: '採用帳號之前保存的編組（捨棄這台裝置上的變更）',
    hint: '此裝置上的變更會自動建立備份分享連結後再被取代，可在「我的分享」找回。',
  },
  {
    value: 'keep-local',
    label: '採用這台裝置目前的編組（覆寫帳號之前保存的）',
    hint: '帳號之前保存的編組會先建立備份分享連結再被覆寫，可在「我的分享」找回。',
  },
] as const

type ChoiceValue = (typeof OPTIONS)[number]['value']

const {
  cloudMerge,
  resolveMergeAppend,
  resolveMergeKeepCloud,
  resolveMergeKeepLocal,
  resolveMergeCancel,
} = useGroupPersistence()
const { heroes, skills } = useData()

const busy = ref(false)
const choice = ref<ChoiceValue>('append')
const ctx = computed(() => cloudMerge.value)

const visible = computed({
  get: () => ctx.value !== null,
  set: (v) => {
    if (!v) resolveMergeCancel()
  },
})

const labeledGroups = (blob: ShareableData | undefined): ShareableGroup[] => {
  if (!blob) return []
  if (blob.workspaces) {
    const tag = (mode: 'free' | 'inventory', g: ShareableGroup): ShareableGroup => ({
      ...g,
      name: `${mode === 'free' ? '自由' : '庫存'} · ${g.name}`,
    })
    return [
      ...(blob.workspaces.free?.groups ?? []).map((g) => tag('free', g)),
      ...(blob.workspaces.inventory?.groups ?? []).map((g) => tag('inventory', g)),
    ]
  }
  return shareableGroupsInBlob(blob)
}

const localCount = computed(() => labeledGroups(ctx.value?.localBlob).length)
const cloudCount = computed(() => ctx.value?.cloudRows.length ?? 0)
const PREVIEW_N = 4
const localPreviewList = computed(() =>
  labeledGroups(ctx.value?.localBlob).slice(0, PREVIEW_N),
)
const cloudPreviewList = computed(() =>
  (ctx.value?.cloudRows ?? []).slice(0, PREVIEW_N),
)
const localOverflow = computed(() => Math.max(0, localCount.value - PREVIEW_N))
const cloudOverflow = computed(() => Math.max(0, cloudCount.value - PREVIEW_N))

// Side-card team count — exclude empty teams (no hero in any role) so the
// number reflects what the user actually built, not the seeded placeholders.
const nonEmptyCount = (teams: ShareableLineup[]): number =>
  teams.reduce((n, t) => (isEmptyShareableLineup(t) ? n : n + 1), 0)

// Preview sub-dialog state. The hydrated groups are computed on demand so
// the heavy ShareableLineup → Lineup conversion only runs when the user
// actually opens the preview.
const localPreviewOpen = ref(false)
const cloudPreviewOpen = ref(false)

interface HydratedGroup { name: string; teams: Lineup[] }

const hydrateGroupList = (
  groups: { name: string; teams: ShareableLineup[] }[],
): HydratedGroup[] =>
  groups
    .map((g) => {
      // Drop empty teams BEFORE hydration so the preview renders only
      // meaningful cards. Group is skipped entirely if every team is empty.
      const nonEmpty = g.teams.filter((t) => !isEmptyShareableLineup(t))
      if (nonEmpty.length === 0) return null
      const result = hydrateShare(
        { v: 4, groups: [{ name: g.name, teams: nonEmpty } as ShareableGroup] },
        { heroes: heroes.value, skills: skills.value },
      )
      // Defensive: hydrateShare may still surface stale Lineup if a JP key
      // doesn't resolve. Filter once more on the hydrated side using the
      // canonical isEmptyTeam.
      const hydrated = result.group
      if (!hydrated) return null
      const teams = hydrated.teams.filter((t) => !isEmptyTeam(t))
      if (teams.length === 0) return null
      return { name: hydrated.name, teams }
    })
    .filter((g): g is HydratedGroup => g !== null)

const localGroupsHydrated = computed<HydratedGroup[]>(() => {
  if (!localPreviewOpen.value || !ctx.value) return []
  return hydrateGroupList(labeledGroups(ctx.value.localBlob))
})

const cloudGroupsHydrated = computed<HydratedGroup[]>(() => {
  if (!cloudPreviewOpen.value || !ctx.value) return []
  return hydrateGroupList(
    ctx.value.cloudRows.map((r) => ({ name: r.name, teams: r.teams })),
  )
})

const openLocalPreview = () => { localPreviewOpen.value = true }
const openCloudPreview = () => { cloudPreviewOpen.value = true }

const showBackupToast = (slug: string | null | undefined, label: string): void => {
  if (slug) {
    ElMessage.success({
      message: `${label}，已建立備份分享連結（在「我的分享」可找到）`,
      duration: 5000,
    })
  } else {
    ElMessage.warning(
      `${label}，但備份分享連結建立失敗，請手動分享後再決定`,
    )
  }
}

const onConfirm = async () => {
  busy.value = true
  try {
    if (choice.value === 'append') {
      await resolveMergeAppend()
      ElMessage.success('已合併兩邊的編組')
    } else if (choice.value === 'keep-cloud') {
      const res = await resolveMergeKeepCloud()
      showBackupToast(res.backupSlug, '已採用帳號之前保存的編組')
    } else if (choice.value === 'keep-local') {
      const res = await resolveMergeKeepLocal()
      showBackupToast(res.backupSlug, '已用此裝置的編組覆寫帳號保存版本')
    }
  } finally {
    busy.value = false
  }
}

const onCancel = () => {
  resolveMergeCancel()
  ElMessage.info('已暫不同步，下次登入會再詢問')
}
</script>

<style scoped>
.side-card {
  background: #ffffff;
  border: 1px solid rgb(var(--color-divider));
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.side-card__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.side-card__tag {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 1px 6px;
  border-radius: 2px;
  color: rgb(var(--color-ink-soft, 71 85 105));
  background: rgb(var(--color-surface-muted));
  border: 1px solid rgb(var(--color-divider));
}
.side-card__tag--cloud {
  color: rgb(var(--color-focus));
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus) / 0.55);
}
.side-card__count {
  margin-left: auto;
  font-size: 13px;
  color: rgb(var(--color-ink-soft, 71 85 105));
}
.side-card__count strong {
  color: rgb(var(--color-ink));
  font-size: 16px;
  font-weight: 700;
}
.side-card__list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 12px;
  color: rgb(var(--color-ink));
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;  /* push the preview button to the bottom regardless of list length */
}
.side-card__preview {
  align-self: flex-start;
}

/* Card-style option row — single click target, top-aligned radio + content,
   active state uses the same gold-on-cream tokens as the rest of the app. */
.option-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: #ffffff;
  border: 1px solid rgb(var(--color-divider));
  border-radius: 8px;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease;
}
.option-card:hover {
  border-color: rgb(var(--color-focus) / 0.45);
}
.option-card--active {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
}
.option-card__radio {
  /* Native radio styled lightly so it sits flush at the top of the row. */
  flex-shrink: 0;
  margin-top: 3px;
  width: 16px;
  height: 16px;
  accent-color: rgb(var(--color-focus));
  cursor: pointer;
}
.option-card__content {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.option-card__title {
  font-size: 14px;
  font-weight: 700;
  color: rgb(var(--color-ink));
  line-height: 1.3;
}
.option-card__hint {
  font-size: 12px;
  color: rgb(var(--color-ink-mute, 148 163 184));
  line-height: 1.5;
}
.option-card--active .option-card__title {
  color: rgb(var(--color-focus));
}
</style>
