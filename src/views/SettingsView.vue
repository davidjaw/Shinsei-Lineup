<template>
  <div class="flex-1 overflow-y-auto px-3 md:px-5 py-4">
    <div class="max-w-3xl flex flex-col gap-6">
      <!-- Cloud sync (Phase C) -->
      <section class="settings-card">
        <header class="settings-card__head">
          <h2 class="font-brand text-xl font-bold text-ink">雲端同步</h2>
          <span class="text-sm text-ink-mute">編組變更會自動同步到此帳號，可在其他裝置繼續編輯</span>
        </header>

        <div v-if="!isLoggedIn" class="text-base text-ink-mute">
          登入後可開啟雲端同步，編組會在裝置間同步。
        </div>

        <template v-else>
          <div class="flex items-center justify-between flex-wrap gap-3">
            <div class="flex flex-col gap-1.5 min-w-0 flex-1">
              <span class="text-base" :class="statusClass">{{ statusLabel }}</span>
              <el-button
                v-if="cloudSyncEnabled && cloudMergeDeferred"
                class="!rounded-sm self-start"
                size="small"
                @click="reopenDeferredMerge"
              >
                立即選擇
              </el-button>
            </div>
            <el-switch
              v-model="syncOn"
              :loading="cloudStatus === 'syncing'"
              size="large"
              inline-prompt
              active-text="開啟"
              inactive-text="關閉"
            />
          </div>

          <ul class="settings-card__notes">
            <li>關閉後本地仍會自動存檔，但不會推到雲端</li>
            <li>多裝置同時編輯若發生衝突，將彈出對話框讓你選擇</li>
            <li>衝突 / 合併時若選擇「捨棄」會自動建立備份分享連結</li>
          </ul>
        </template>
      </section>

      <section class="settings-card">
        <header class="settings-card__head">
          <h2 class="font-brand text-xl font-bold text-ink">其他設定</h2>
          <span class="text-sm text-ink-mute">語系 / 配色 / 帳號 — 尚未實作</span>
        </header>
        <p class="text-base text-ink-mute">將陸續上線。</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuth } from '../composables/useAuth'
import { useGroupPersistence } from '../composables/useGroupPersistence'

const { isLoggedIn } = useAuth()
const {
  cloudSyncEnabled,
  cloudStatus,
  cloudMergeDeferred,
  setCloudSyncEnabled,
  reopenDeferredMerge,
} = useGroupPersistence()

const syncOn = computed({
  get: () => cloudSyncEnabled.value,
  set: (v) => setCloudSyncEnabled(v),
})

const statusLabel = computed(() => {
  if (!cloudSyncEnabled.value) return '目前狀態：已關閉'
  if (cloudMergeDeferred.value) return '目前狀態：登入合併尚未決定，雲端同步暫停中'
  switch (cloudStatus.value) {
    case 'syncing': return '目前狀態：同步中…'
    case 'conflict': return '目前狀態：發生衝突，請於對話框處理'
    case 'offline': return '目前狀態：雲端連線異常（會在下次編輯重試）'
    case 'error': return '目前狀態：寫入失敗，請稍後再試'
    case 'idle':
    default:       return '目前狀態：閒置'
  }
})

const statusClass = computed(() => {
  if (!cloudSyncEnabled.value) return 'text-ink-mute'
  if (cloudMergeDeferred.value) return 'text-amber-700'
  switch (cloudStatus.value) {
    case 'syncing': return 'text-focus'
    case 'conflict':
    case 'error':   return 'text-red-600'
    case 'offline': return 'text-amber-700'
    default:        return 'text-ink-mute'
  }
})
</script>

<style scoped>
.settings-card {
  background: #ffffff;
  border: 1px solid rgb(var(--color-divider));
  border-radius: 10px;
  padding: 20px 22px;
}
.settings-card__head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgb(var(--color-divider));
  flex-wrap: wrap;
}
.settings-card__notes {
  list-style: disc;
  padding-left: 22px;
  margin: 16px 0 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  line-height: 1.55;
  color: rgb(var(--color-ink-mute, 148 163 184));
}
</style>
