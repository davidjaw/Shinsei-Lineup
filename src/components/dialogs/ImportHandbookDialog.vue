<template>
  <el-dialog
    v-model="visible"
    title="從官方圖鑑網址導入庫存"
    width="480px"
    align-center
    :close-on-click-modal="!committing"
    :close-on-press-escape="!committing"
    :before-close="onBeforeClose"
    @opened="onOpened"
    @closed="onClosed"
  >
    <div v-if="phase === 'input'" class="flex flex-col gap-3">
      <p class="text-sm text-ink-soft leading-relaxed">
        貼上賽利亞站台圖鑑分享連結（含 <code class="text-xs px-1 bg-surface-muted rounded">snapshot_id</code>）。
        只匯入擁有的武將／戰法名單，不會改動編組。
      </p>
      <el-input
        ref="inputRef"
        v-model="rawInput"
        placeholder="https://general.sialiagamesinc.com.tw/…#/handbook?snapshot_id=…"
        clearable
        @keyup.enter="onLoad"
      />
    </div>

    <div v-else-if="phase === 'loading'" class="text-center py-8 text-sm text-ink-mute">
      <el-icon class="is-loading mr-1.5" :size="16"><Loading /></el-icon>
      載入中…
    </div>

    <div v-else-if="phase === 'error'" class="flex flex-col gap-3">
      <el-alert :title="errorMessage" type="error" :closable="false" show-icon />
      <el-button @click="resetToInput" plain class="!rounded-sm">重新輸入</el-button>
    </div>

    <div v-else-if="phase === 'ready' && mapped" class="flex flex-col gap-3">
      <p class="text-sm text-ink leading-relaxed">
        找到
        <strong>{{ mapped.chtHeroes.length }}</strong> 武將、
        <strong>{{ mapped.chtSkills.length }}</strong> 戰法
        <span v-if="snap?.player_id" class="text-ink-mute">（玩家 {{ snap.player_id }}）</span>
      </p>
      <el-alert
        v-if="unmatchedCount > 0"
        type="warning"
        :closable="false"
        show-icon
        :title="`有 ${unmatchedCount} 筆尚未收錄於本站圖鑑，匯入時會略過`"
      />

      <label
        class="option-card"
        :class="{ 'option-card--active': action === 'overwrite' }"
      >
        <input v-model="action" type="radio" value="overwrite" class="option-card__radio" />
        <span class="option-card__content">
          <span class="option-card__title">覆蓋目前庫存</span>
          <span class="option-card__hint">
            取代現在這份擁有名單。自由模式的編組不會被改到。
          </span>
        </span>
      </label>

      <label
        v-if="isLoggedIn"
        class="option-card"
        :class="{ 'option-card--active': action === 'create' }"
      >
        <input v-model="action" type="radio" value="create" class="option-card__radio" />
        <span class="option-card__content">
          <span class="option-card__title">另存為新配置</span>
          <span class="option-card__hint">建成角色配置並切換過去。</span>
        </span>
      </label>
      <p v-else class="text-xs text-ink-mute">未登入只能覆蓋目前庫存（本次階段）。</p>

      <el-input
        v-if="action === 'create'"
        v-model="createName"
        maxlength="50"
        show-word-limit
        placeholder="為這個配置取名（必填）"
        @keyup.enter="onConfirm"
      />

      <el-checkbox
        v-if="action === 'overwrite' && isLoggedIn && activeProfileName"
        v-model="syncActiveProfile"
      >
        同步更新角色配置「{{ activeProfileName }}」
      </el-checkbox>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2 flex-wrap">
        <el-button class="!rounded-sm" :disabled="committing" @click="visible = false">取消</el-button>
        <el-button
          v-if="phase === 'input'"
          type="primary"
          class="!rounded-sm"
          :disabled="!canLoad"
          @click="onLoad"
        >載入</el-button>
        <el-button
          v-else-if="phase === 'ready'"
          type="primary"
          class="!rounded-sm"
          :loading="committing"
          :disabled="!canConfirm"
          @click="onConfirm"
        >導入並切換到庫存模式</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useData } from '../../composables/useData'
import { fetchHandbookSnapshot, type HandbookSnapshot } from '../../lib/handbookFetch'
import {
  mapHandbookInventory,
  parseSnapshotId,
  type MappedHandbookInventory,
} from '../../lib/handbookSnapshot'

export type ImportHandbookAction = 'overwrite' | 'create'

export interface ImportHandbookPayload {
  action: ImportHandbookAction
  chtHeroes: string[]
  chtSkills: string[]
  inv_h: string[]
  inv_s: string[]
  name?: string
  syncActiveProfile: boolean
  unmatchedHeroes: number
  unmatchedSkills: number
}

const props = defineProps<{
  modelValue: boolean
  isLoggedIn: boolean
  activeProfileName: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'import', payload: ImportHandbookPayload): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

type Phase = 'input' | 'loading' | 'error' | 'ready'
const phase = ref<Phase>('input')
const rawInput = ref('')
const errorMessage = ref('')
const snap = ref<HandbookSnapshot | null>(null)
const mapped = ref<MappedHandbookInventory | null>(null)
const action = ref<ImportHandbookAction>('overwrite')
const createName = ref('')
const syncActiveProfile = ref(true)
const committing = ref(false)
const inputRef = ref<{ focus?: () => void } | null>(null)

const { heroes, skills } = useData()

const canLoad = computed(() => parseSnapshotId(rawInput.value) != null)
const unmatchedCount = computed(() =>
  (mapped.value?.unmatchedHeroes.length ?? 0) + (mapped.value?.unmatchedSkills.length ?? 0),
)
const canConfirm = computed(() => {
  if (committing.value) return false
  if (!mapped.value) return false
  if (mapped.value.chtHeroes.length === 0 && mapped.value.chtSkills.length === 0) return false
  if (action.value === 'create' && !createName.value.trim()) return false
  return true
})

const resetToInput = () => {
  phase.value = 'input'
  errorMessage.value = ''
  snap.value = null
  mapped.value = null
  committing.value = false
}

const onOpened = () => {
  resetToInput()
  action.value = 'overwrite'
  createName.value = ''
  syncActiveProfile.value = true
  void nextTick(() => inputRef.value?.focus?.())
}

const onClosed = () => {
  resetToInput()
  rawInput.value = ''
}

const onBeforeClose = (done: () => void) => {
  if (committing.value) return
  done()
}

const onLoad = async () => {
  const id = parseSnapshotId(rawInput.value)
  if (!id) {
    errorMessage.value = '請貼上含 snapshot_id 的圖鑑連結'
    phase.value = 'error'
    return
  }
  phase.value = 'loading'
  try {
    const fetched = await fetchHandbookSnapshot(id)
    const result = mapHandbookInventory(fetched, heroes.value, skills.value)
    if (result.chtHeroes.length === 0 && result.chtSkills.length === 0) {
      errorMessage.value = '此快照沒有可對應到本站圖鑑的武將或戰法'
      phase.value = 'error'
      return
    }
    snap.value = fetched
    mapped.value = result
    phase.value = 'ready'
  } catch (e) {
    errorMessage.value = (e as Error).message || '載入失敗'
    phase.value = 'error'
  }
}

const onConfirm = () => {
  const m = mapped.value
  if (committing.value || !m || !canConfirm.value) return
  committing.value = true
  emit('import', {
    action: action.value,
    chtHeroes: m.chtHeroes,
    chtSkills: m.chtSkills,
    inv_h: m.inv_h,
    inv_s: m.inv_s,
    name: action.value === 'create' ? createName.value.trim() : undefined,
    syncActiveProfile: action.value === 'overwrite' && syncActiveProfile.value,
    unmatchedHeroes: m.unmatchedHeroes.length,
    unmatchedSkills: m.unmatchedSkills.length,
  })
}

const setCommitting = (v: boolean) => { committing.value = v }
defineExpose({ setCommitting })
</script>

<style scoped>
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

