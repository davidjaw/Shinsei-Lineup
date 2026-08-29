<template>
  <div class="variant-card">
    <!-- Head row: author meta on the left, action cluster on the right.
         Putting actions inline with the author trims the card's vertical
         footprint and frees the bottom for the variant content itself. -->
    <div class="head">
      <div class="head-left">
        <span
          v-if="publicTitle.text !== null && publicTitle.locked"
          class="team-title"
        >
          <SpoilerText locked />
        </span>
        <span
          v-else-if="publicTitle.text !== null && publicTitle.hidden"
          class="team-title"
        >
          <SpoilerText>{{ publicTitle.text }}</SpoilerText>
        </span>
        <span
          v-else-if="publicTitle.text !== null"
          class="team-title"
          :title="publicTitle.text"
        >{{ publicTitle.text }}</span>
        <span class="author">
          <span class="author-prefix">原作</span>
          <strong class="author-name">
            <UserTag
              :name="firstAuthorParts.name"
              :user-id="firstAuthorParts.userId"
              :hidden="firstAuthorParts.hidden"
              :locked="firstAuthorParts.locked"
            />
          </strong>
        </span>
        <el-tooltip
          v-if="contributorCount > 1"
          placement="top"
          effect="dark"
          :content="contributorTooltip"
        >
          <span class="chip chip--contrib">+{{ contributorCount - 1 }} 貢獻者</span>
        </el-tooltip>
        <span v-if="isMyContribution" class="chip chip--mine" title="你曾提交此配置">
          我的
        </span>
        <span class="time" :title="`首次提交：${variant.firstSubmittedAt}`">
          · {{ relativeTime(variant.updatedAt) }}
        </span>
      </div>
      <div class="head-right">
        <el-dropdown
          v-if="showModeration"
          trigger="click"
          @command="onModerationCommand"
        >
          <button type="button" class="icon-btn report-btn" title="檢舉" aria-label="檢舉">
            {{ isAdmin ? '管理' : '檢舉' }}
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="team_name" :disabled="teamNameReportDisabled">
                檢舉隊伍名稱
              </el-dropdown-item>
              <el-dropdown-item command="display_name" :disabled="authorNameReportDisabled">
                檢舉作者名稱
              </el-dropdown-item>
              <el-dropdown-item
                v-if="isAdmin && !publicTitle.locked"
                command="admin_team_name"
                divided
                :disabled="!publicTitle.sourceUserId"
              >
                {{ publicTitle.hidden ? '顯示隊伍名稱' : '隱藏隊伍名稱' }}
              </el-dropdown-item>
              <el-dropdown-item
                v-if="isAdmin"
                command="admin_lock_team_name"
                :divided="publicTitle.locked"
                :disabled="!publicTitle.sourceUserId"
              >
                {{ publicTitle.locked ? '解除永久隱藏隊伍名稱' : '永久隱藏隊伍名稱' }}
              </el-dropdown-item>
              <el-dropdown-item
                v-if="isAdmin && !firstAuthorParts.locked"
                command="admin_display_name"
                :disabled="!firstAuthorParts.userId"
              >
                {{ firstAuthorParts.hidden ? '顯示作者名稱' : '隱藏作者名稱' }}
              </el-dropdown-item>
              <el-dropdown-item
                v-if="isAdmin"
                command="admin_lock_display_name"
                :disabled="!firstAuthorParts.userId"
              >
                {{ firstAuthorParts.locked ? '解除永久隱藏作者名稱' : '永久隱藏作者名稱' }}
              </el-dropdown-item>
              <el-dropdown-item
                v-if="isAdmin"
                command="admin_ban"
                divided
                :disabled="!firstAuthorParts.userId"
              >
                {{ authorBanned ? '解除封鎖' : '封鎖此作者' }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-popconfirm
          v-if="isMyContribution"
          title="撤回你對此配置的提交？若你是最後一位貢獻者，整個變體將被刪除"
          confirm-button-text="撤回"
          cancel-button-text="取消"
          confirm-button-type="danger"
          :width="280"
          @confirm="$emit('withdraw')"
        >
          <template #reference>
            <button
              type="button"
              class="icon-btn icon-btn--danger"
              title="撤回我的提交"
              aria-label="撤回我的提交"
            >
              <el-icon :size="14"><CircleClose /></el-icon>
            </button>
          </template>
        </el-popconfirm>
        <button
          type="button"
          class="action-btn action-btn--icon"
          title="匯入到編組"
          aria-label="匯入到編組"
          @click="$emit('import-to-group')"
        >
          <el-icon :size="14"><Position /></el-icon>
        </button>
        <button
          type="button"
          class="action-btn action-btn--vote"
          :class="{ 'action-btn--up': votedDirection === 1, 'action-btn--disabled': !canVote }"
          :disabled="!canVote"
          :title="voteTooltip"
          @click="$emit('upvote')"
        >
          <el-icon :size="14"><CaretTop /></el-icon>
          <span>{{ variant.upvoteCount }}</span>
        </button>
        <button
          type="button"
          class="action-btn action-btn--vote"
          :class="{ 'action-btn--down': votedDirection === -1, 'action-btn--disabled': !canVote }"
          :disabled="!canVote"
          :title="voteTooltip"
          @click="$emit('downvote')"
        >
          <el-icon :size="14"><CaretBottom /></el-icon>
          <span>{{ variant.downvoteCount }}</span>
        </button>
      </div>
    </div>

    <!-- TeamSkillsPreview now embeds its own watermark as the bottom edge
         of the skills table, so the card body proper ends with brand —
         the bingxue strip sits below as a separate block. -->
    <TeamSkillsPreview :team="normalizedTeam" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CaretTop, CaretBottom, Position, CircleClose } from '@element-plus/icons-vue'
import type { ReportKind, Variant, VariantContributor } from '../../lib/variants'
import { withCanonicalViceOrder } from '../../lib/lineup'
import { relativeTime } from '../../lib/time'
import { resolveAuthorLabel, resolveAuthorParts, resolvePublicTeamTitle } from '../../lib/displayName'
import TeamSkillsPreview from './TeamSkillsPreview.vue'
import UserTag from '../UserTag.vue'
import SpoilerText from '../SpoilerText.vue'

const props = withDefaults(defineProps<{
  variant: Variant
  firstAuthorName?: string | null
  contributors?: VariantContributor[]
  votedDirection: -1 | 1 | null
  isMyContribution: boolean
  isLoggedIn: boolean
  currentUserId?: string | null
  isAdmin?: boolean
  authorBanned?: boolean
}>(), {
  currentUserId: null,
  isAdmin: false,
  authorBanned: false,
})

const emit = defineEmits<{
  (e: 'upvote'): void
  (e: 'downvote'): void
  (e: 'import-to-group'): void
  (e: 'withdraw'): void
  (e: 'report', payload: { kind: ReportKind; targetUserId: string }): void
  (e: 'admin-set', payload: { kind: ReportKind; targetUserId: string; hidden: boolean; locked?: boolean }): void
  (e: 'admin-ban', payload: { userId: string; banned: boolean }): void
}>()

const normalizedTeam = computed(() => withCanonicalViceOrder(props.variant.team))

const contributorList = computed(() => props.contributors ?? [])

const publicTitle = computed(() =>
  resolvePublicTeamTitle(props.variant.firstAuthorId, contributorList.value),
)

const firstAuthorContributor = computed<VariantContributor | null>(() => {
  const list = contributorList.value
  const id = props.variant.firstAuthorId
  if (id) {
    const match = list.find(c => c.userId === id)
    if (match) return match
  }
  return list[0] ?? null
})

const firstAuthorParts = computed(() =>
  resolveAuthorParts(firstAuthorContributor.value, props.variant.firstAuthorId),
)

const contributorCount = computed(() => contributorList.value.length)

const contributorTooltip = computed(() =>
  contributorList.value.map(c => resolveAuthorLabel(c)).join('、'),
)

const teamNameReportDisabled = computed(() => {
  const t = publicTitle.value
  return t.text === null || t.hidden || t.sourceUserId === props.currentUserId
})

const authorNameReportDisabled = computed(() => {
  const id = firstAuthorParts.value.userId
  return !id || firstAuthorParts.value.hidden || id === props.currentUserId
})

const showModeration = computed(() =>
  Boolean(props.currentUserId)
  && (props.isAdmin || !teamNameReportDisabled.value || !authorNameReportDisabled.value),
)

const onModerationCommand = (command: string) => {
  if (command === 'admin_team_name') {
    const id = publicTitle.value.sourceUserId
    if (!id || !props.isAdmin) return
    emit('admin-set', { kind: 'team_name', targetUserId: id, hidden: !publicTitle.value.hidden })
    return
  }
  if (command === 'admin_lock_team_name') {
    const id = publicTitle.value.sourceUserId
    if (!id || !props.isAdmin) return
    const locking = !publicTitle.value.locked
    emit('admin-set', { kind: 'team_name', targetUserId: id, hidden: locking, locked: locking })
    return
  }
  if (command === 'admin_display_name') {
    const id = firstAuthorParts.value.userId
    if (!id || !props.isAdmin) return
    emit('admin-set', { kind: 'display_name', targetUserId: id, hidden: !firstAuthorParts.value.hidden })
    return
  }
  if (command === 'admin_lock_display_name') {
    const id = firstAuthorParts.value.userId
    if (!id || !props.isAdmin) return
    const locking = !firstAuthorParts.value.locked
    emit('admin-set', { kind: 'display_name', targetUserId: id, hidden: locking, locked: locking })
    return
  }
  if (command === 'admin_ban') {
    const id = firstAuthorParts.value.userId
    if (!id || !props.isAdmin) return
    emit('admin-ban', { userId: id, banned: !props.authorBanned })
    return
  }
  const kind = command as ReportKind
  if (kind === 'team_name') {
    const id = publicTitle.value.sourceUserId
    if (!id || teamNameReportDisabled.value) return
    emit('report', { kind, targetUserId: id })
    return
  }
  const id = firstAuthorParts.value.userId
  if (!id || authorNameReportDisabled.value) return
  emit('report', { kind, targetUserId: id })
}

const canVote = computed(() => props.isLoggedIn && !props.isMyContribution)
const voteTooltip = computed(() => {
  if (canVote.value) return ''
  if (props.isMyContribution) return '無法為自己參與的變體投票'
  return '登入後可投票'
})
</script>

<style scoped>
.variant-card {
  background: linear-gradient(180deg, #FFFBF1 0%, #FFFFFF 22%, #FFFFFF 100%);
  border: 1px solid rgb(var(--color-divider));
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(180, 83, 9, 0.06);
  transition: box-shadow 0.18s ease, border-color 0.18s ease;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.variant-card:hover {
  border-color: rgba(180, 83, 9, 0.4);
  box-shadow: 0 6px 18px rgba(180, 83, 9, 0.10), 0 2px 4px rgba(0, 0, 0, 0.05);
}

/* Head row: text-heavy left, action cluster right. Wrap on narrow widths
   so actions drop below author info instead of crushing. */
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: rgb(var(--color-ink-mute));
}
.head-left {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1 1 auto;
  flex-wrap: wrap;
}
.team-title {
  max-width: 12em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 700;
  color: rgb(var(--color-ink));
  flex-shrink: 1;
}
.author {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  overflow: hidden;
}
.author-prefix {
  font-size: 11px;
  color: rgb(var(--color-ink-mute));
  letter-spacing: 1px;
  flex-shrink: 0;
}
.author-name {
  display: inline-flex;
  min-width: 0;
  max-width: 16em;
  font-size: 14px;
  font-weight: 700;
  color: #92400e;
}

.chip {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3px;
}
.chip--contrib {
  background: #f3f4f6;
  border: 1px solid rgb(var(--color-divider));
  color: rgb(var(--color-ink-soft));
  cursor: help;
}
.chip--mine {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border: 1px solid #f59e0b;
  color: #92400e;
}

.time {
  font-size: 11px;
  color: rgb(var(--color-ink-mute));
  font-variant-numeric: tabular-nums;
}

.head-right {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: rgb(var(--color-ink-mute));
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.icon-btn:hover {
  background: rgb(var(--color-highlight));
  color: rgb(var(--color-ink));
}
.icon-btn--danger:hover {
  background: #fee2e2;
  color: #b91c1c;
  border-color: #fca5a5;
}
.report-btn {
  width: auto;
  min-width: 28px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #ffffff;
  border: 1px solid rgb(var(--color-divider));
  color: rgb(var(--color-ink-soft));
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s;
  font-variant-numeric: tabular-nums;
}
.action-btn:hover:not(.action-btn--disabled) {
  background: rgb(var(--color-highlight));
  border-color: rgb(var(--color-focus));
}
.action-btn--up {
  background: linear-gradient(180deg, #fef3c7 0%, #fde68a 100%);
  border-color: #f59e0b;
  color: #b45309;
  box-shadow: 0 1px 2px rgba(245, 158, 11, 0.2);
}
.action-btn--down {
  background: #e0e7ff;
  border-color: #6366f1;
  color: #3730a3;
}
.action-btn--disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.action-btn--icon { padding: 4px 9px; }
</style>
