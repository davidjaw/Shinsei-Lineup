<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    :title="dialogTitle"
    width="560px"
    align-center
  >
    <template v-if="source">
      <p class="text-sm text-ink-soft mb-4 leading-relaxed">
        將「<span class="font-bold text-ink">{{ source.displayName }}</span>」
        匯入到目標編組。容量已滿的編組會被停用。
      </p>

      <!-- Destination picker — one VersionCard row per group. -->
      <div v-if="destOptions.length > 0" class="flex flex-col gap-2 mb-4">
        <div
          v-for="opt in destOptions"
          :key="opt.id"
          class="dest-row"
          :class="{
            'dest-row--full': opt.isFull,
            'dest-row--selected': selectedIdx === opt.idx,
          }"
          role="button"
          :tabindex="opt.isFull ? -1 : 0"
          :aria-disabled="opt.isFull"
          @click="opt.isFull ? null : (selectedIdx = opt.idx)"
          @keydown.enter.prevent="opt.isFull ? null : (selectedIdx = opt.idx)"
          @keydown.space.prevent="opt.isFull ? null : (selectedIdx = opt.idx)"
        >
          <VersionCard
            :name="opt.name"
            :tag="opt.isFull ? '已滿' : '編組'"
            :tag-variant="selectedIdx === opt.idx ? 'highlight' : 'default'"
          >
            <template #meta>
              <span><strong>{{ opt.teamCount }}</strong> / {{ maxTeams }} 隊</span>
              <span v-if="opt.idx === selectedIdx && hasAnyConflict" class="conflict-meta">
                {{ collisionSummary }}
              </span>
            </template>
          </VersionCard>
        </div>
      </div>

      <p v-else class="text-sm text-ink-mute py-6 text-center">
        尚無其他編組可作為匯入目標。請先在「我的編組」建立新編組。
      </p>

      <!-- Conflict resolution radio — only when the selected destination has
           heroes/skills that collide with the incoming team. Mirrors the
           legacy ImportProposalDialog UX so the choice surface stays
           familiar. -->
      <div
        v-if="hasAnyConflict"
        class="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 leading-snug mb-2"
      >
        <p class="font-bold mb-1">與「{{ selectedGroupName }}」其它隊伍重複</p>
        <p v-if="collisionPreview.heroes.length > 0">
          武將：<span class="font-mono">{{ collisionPreview.heroes.join('、') }}</span>
        </p>
        <p v-if="collisionPreview.skills.length > 0">
          戰法：<span class="font-mono">{{ collisionPreview.skills.join('、') }}</span>
        </p>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2 flex-wrap">
        <el-button class="!rounded-sm" @click="onCancel">取消</el-button>
        <template v-if="!hasAnyConflict">
          <el-button
            type="primary"
            class="!rounded-sm"
            :disabled="!canConfirm"
            @click="onConfirm('overwrite')"
          >匯入到「{{ selectedGroupName || '—' }}」</el-button>
        </template>
        <template v-else>
          <el-button class="!rounded-sm" :disabled="!canConfirm" @click="onConfirm('leave-empty')">
            留空匯入
          </el-button>
          <el-button
            type="primary"
            class="!rounded-sm"
            :disabled="!canConfirm"
            @click="onConfirm('overwrite')"
          >從原隊移除</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useGroups } from '../../composables/useGroups'
import { MAX_TEAMS_PER_GROUP } from '../../types/group'
import type { Lineup } from '../../composables/useLineups'
import type { ImportConflictResolution } from '../../types/group'
import { buildCollisionPool, previewCollisions } from '../../lib/teamConflicts'
import VersionCard from '../preview/VersionCard.vue'

export interface ExportSource {
  team: Lineup
  displayName: string
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    source: ExportSource | null
    /** Group id to exclude from the destination list (e.g. the current
     *  group when invoked from the lineup builder, where "export to other"
     *  semantically excludes self). Intentionally omitted by the proposals-
     *  page caller — all groups are valid import destinations there. */
    excludeGroupId?: string
    /** Group id to pre-select when the dialog opens. Used by the proposals
     *  page to default to the user's active group — without it, the dialog
     *  picks the first non-full group and may surface conflicts against an
     *  unrelated group the user isn't currently working in. */
    defaultGroupId?: string
    /** UX framing — purely cosmetic. 'export' = "send my team elsewhere"
     *  (builder side); 'import' = "pull this team into a group" (proposals
     *  side). Drives the dialog title and nothing else. */
    variant?: 'export' | 'import'
  }>(),
  { variant: 'export' },
)
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'exported', payload: {
    destGroupIdx: number
    resolution: ImportConflictResolution
  }): void
}>()

const { groups } = useGroups()
const maxTeams = MAX_TEAMS_PER_GROUP

const selectedIdx = ref<number | null>(null)

interface DestOption {
  idx: number
  id: string
  name: string
  teamCount: number
  isFull: boolean
}

const destOptions = computed<DestOption[]>(() =>
  groups.value
    .map((g, idx) => ({
      idx,
      id: g.id,
      name: g.name,
      teamCount: g.teams.length,
      isFull: g.teams.length >= maxTeams,
    }))
    .filter((o) => o.id !== props.excludeGroupId),
)

// Re-select on open. Prefer `defaultGroupId` (caller's "active context"
// hint — e.g. the user's current group on the proposals page) so the
// initial conflict check reflects where the user is actually working,
// rather than an unrelated first-available group. Fall back to first
// non-full when the hint is missing or full.
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    const preferred =
      props.defaultGroupId != null
        ? destOptions.value.find(
            (o) => o.id === props.defaultGroupId && !o.isFull,
          )
        : undefined
    const fallback = destOptions.value.find((o) => !o.isFull)
    const picked = preferred ?? fallback
    selectedIdx.value = picked ? picked.idx : null
  },
)

const selectedGroup = computed(() =>
  selectedIdx.value != null ? groups.value[selectedIdx.value] ?? null : null,
)
const selectedGroupName = computed(() => selectedGroup.value?.name ?? '')

// Pool depends only on the destination group's teams. Splitting it out
// avoids rebuilding when the source team prop changes but the destination
// stays the same.
const collisionPool = computed(() => {
  const g = selectedGroup.value
  return g ? buildCollisionPool(g.teams) : null
})

const collisionPreview = computed<{ heroes: string[]; skills: string[] }>(() => {
  const t = props.source?.team
  const pool = collisionPool.value
  if (!t || !pool) return { heroes: [], skills: [] }
  return previewCollisions(t, pool)
})

const hasAnyConflict = computed(
  () =>
    collisionPreview.value.heroes.length > 0 ||
    collisionPreview.value.skills.length > 0,
)

const collisionSummary = computed(() => {
  const { heroes, skills } = collisionPreview.value
  const parts: string[] = []
  if (heroes.length > 0) parts.push(`武將×${heroes.length}`)
  if (skills.length > 0) parts.push(`戰法×${skills.length}`)
  return parts.length > 0 ? `衝突 ${parts.join(' / ')}` : ''
})

// Title shifts copy slightly depending on caller intent — same dialog,
// different mental model. Lineup builder = "export out"; proposals = "import in".
const dialogTitle = computed(() =>
  props.variant === 'import' ? '匯入到編組' : '導出到其他編組',
)

const canConfirm = computed(() => {
  if (!props.source) return false
  if (selectedIdx.value == null) return false
  const g = selectedGroup.value
  if (!g) return false
  if (g.teams.length >= maxTeams) return false
  return true
})

const onCancel = () => emit('update:modelValue', false)

const onConfirm = (resolution: ImportConflictResolution) => {
  if (!canConfirm.value || selectedIdx.value == null) return
  emit('exported', { destGroupIdx: selectedIdx.value, resolution })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.dest-row {
  cursor: pointer;
  border-radius: 8px;
  transition: transform 0.12s ease, opacity 0.12s ease;
}
.dest-row:hover:not(.dest-row--full) :deep(.version-card) {
  border-color: rgb(var(--color-focus));
  background: rgb(var(--color-highlight) / 0.4);
}
.dest-row--selected :deep(.version-card) {
  border-color: rgb(var(--color-focus));
  background: rgb(var(--color-highlight));
}
.dest-row--full {
  cursor: not-allowed;
  opacity: 0.5;
  pointer-events: none;
}
.conflict-meta {
  color: rgb(180 83 9);
  font-weight: 700;
}
</style>
