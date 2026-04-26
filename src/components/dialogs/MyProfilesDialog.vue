<template>
  <el-dialog v-model="visible" title="我的角色配置" width="720px" align-center append-to-body>
    <div v-loading="loading" class="min-h-[160px]">
      <!-- Header actions -->
      <div class="flex items-center gap-2 mb-3 flex-wrap">
        <el-button type="primary" plain :icon="Plus" @click="openCreateDialog">
          儲存目前庫存為新配置
        </el-button>
        <el-button :icon="Link" @click="openImportDialog">從分享連結匯入</el-button>
        <span class="ml-auto text-[11px] text-gray-400">
          配置只存庫存（武將/戰法），不含隊伍配置
        </span>
      </div>

      <p
        v-if="!loading && profiles.length === 0"
        class="text-center text-gray-400 py-8 text-sm"
      >
        還沒有任何角色配置。<br>
        在主畫面編輯庫存後，點上方按鈕儲存為配置。
      </p>

      <el-table v-else-if="profiles.length > 0" :data="profiles" size="default" style="width: 100%">
        <el-table-column label="" width="44" align="center">
          <template #default="{ row }">
            <button
              @click="toggleDefault(row)"
              :title="row.is_default ? '取消預設' : '設為預設'"
              class="default-btn"
              :class="{ 'default-btn-on': row.is_default }"
            >
              <el-icon><component :is="row.is_default ? StarFilled : Star" /></el-icon>
            </button>
          </template>
        </el-table-column>

        <el-table-column label="名稱" min-width="160">
          <template #default="{ row }">
            <div v-if="editingId === row.id" class="flex items-center gap-1">
              <el-input
                v-model="editingDraft"
                size="small"
                maxlength="50"
                placeholder="輸入名稱"
                @keyup.enter="saveRename(row)"
                @keyup.esc="cancelRename"
                autofocus
              />
              <el-button size="small" type="primary" :icon="Check" @click="saveRename(row)" />
              <el-button size="small" :icon="Close" @click="cancelRename" />
            </div>
            <div v-else class="flex items-center gap-2 group">
              <span class="text-gray-800 font-medium truncate">{{ row.name }}</span>
              <span
                v-if="activeProfileId === row.id"
                class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 flex-shrink-0"
              >使用中</span>
              <el-button
                text
                size="small"
                :icon="Edit"
                class="opacity-0 group-hover:opacity-100"
                @click="startRename(row)"
              />
            </div>
          </template>
        </el-table-column>

        <el-table-column label="庫存" width="120" align="center">
          <template #default="{ row }">
            <div class="text-xs text-gray-500 leading-tight">
              <div>{{ row.inv_h.length }} 武將</div>
              <div>{{ row.inv_s.length }} 戰法</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="更新" width="90">
          <template #default="{ row }">
            <span class="text-xs text-gray-500">{{ relativeTime(row.updated_at) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="" width="200" align="right">
          <template #default="{ row }">
            <div class="flex items-center justify-end gap-1">
              <el-button
                size="small"
                type="primary"
                @click="onApplyClick(row)"
              >
                套用
              </el-button>
              <el-tooltip content="用目前庫存覆寫此配置" placement="top">
                <el-button size="small" :icon="RefreshRight" @click="overwriteWithCurrent(row)" />
              </el-tooltip>
              <el-popconfirm
                title="確定刪除這個配置？刪除後無法復原。"
                confirm-button-text="刪除"
                cancel-button-text="取消"
                confirm-button-type="danger"
                @confirm="removeProfile(row)"
              >
                <template #reference>
                  <el-button size="small" type="danger" :icon="Delete" />
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Create-profile sub-dialog (asks for name) -->
    <el-dialog
      v-model="createDialogVisible"
      title="儲存目前庫存"
      width="340px"
      align-center
      append-to-body
    >
      <div class="flex flex-col gap-3 pb-1">
        <p class="text-xs text-gray-500 -mt-1 leading-relaxed">
          將目前庫存（{{ ownedHeroes.length }} 武將, {{ ownedSkills.length }} 戰法）儲存為新配置
        </p>
        <el-input
          v-model="createName"
          maxlength="50"
          show-word-limit
          placeholder="例：主帳、小號、朋友A"
          @keyup.enter="submitCreate"
          autofocus
        />
        <el-checkbox v-model="createAsDefault">設為預設配置</el-checkbox>
        <el-button
          type="primary"
          :loading="createSaving"
          @click="submitCreate"
          class="w-full !m-0"
        >
          儲存
        </el-button>
      </div>
    </el-dialog>

    <!-- Import-from-share-link sub-dialog -->
    <el-dialog
      v-model="importDialogVisible"
      title="從分享連結匯入配置"
      width="380px"
      align-center
      append-to-body
    >
      <div class="flex flex-col gap-3 pb-1">
        <p class="text-xs text-gray-500 -mt-1 leading-relaxed">
          貼上對方分享給你的連結（必須包含庫存資訊）。匯入後成為你的角色配置。
        </p>
        <el-input
          v-model="importUrl"
          placeholder="https://...#s/xxx 或 https://...#xxxx"
          clearable
          autofocus
        />
        <el-input
          v-model="importName"
          maxlength="50"
          show-word-limit
          placeholder="為這個配置取名（必填）"
          @keyup.enter="submitImport"
        />
        <el-button
          type="primary"
          :loading="importLoading"
          @click="submitImport"
          class="w-full !m-0"
        >
          匯入
        </el-button>
      </div>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Link, Edit, Close, Check, Delete, Star, StarFilled, RefreshRight,
} from '@element-plus/icons-vue'
import {
  listMyProfiles, createProfile, renameProfile, updateProfileInventory,
  setDefaultProfile, deleteProfile, type Profile,
} from '../../lib/profiles'
import { loadShare } from '../../lib/share'
import { useData } from '../../composables/useData'
import { useInventory } from '../../composables/useInventory'
import { useActiveProfile } from '../../composables/useActiveProfile'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const { heroes, skills } = useData()
const { ownedHeroes, ownedSkills, isEditingInventory } = useInventory()
const {
  applyProfile, syncActiveProfile, activeProfileId, activeProfile,
} = useActiveProfile()

const profiles = ref<Profile[]>([])
const loading = ref(false)

// Inline rename (matches MyShares dialog pattern).
const editingId = ref<string | null>(null)
const editingDraft = ref('')

// Create-profile sub-dialog
const createDialogVisible = ref(false)
const createName = ref('')
const createAsDefault = ref(false)
const createSaving = ref(false)

// Import-from-share-link sub-dialog
const importDialogVisible = ref(false)
const importUrl = ref('')
const importName = ref('')
const importLoading = ref(false)

// JP-name lookup for current inventory. Built once per data load and reused.
const heroChtToJp = computed(() => new Map(heroes.value.map(h => [h.name, h.name_jp])))
const skillChtToJp = computed(() => new Map(skills.value.map(s => [s.name, s.name_jp])))

const currentInventoryAsJP = (): { inv_h: string[]; inv_s: string[] } => ({
  inv_h: ownedHeroes.value.map(n => heroChtToJp.value.get(n) ?? n),
  inv_s: ownedSkills.value.map(n => skillChtToJp.value.get(n) ?? n),
})

const refresh = async () => {
  loading.value = true
  try {
    profiles.value = await listMyProfiles()
    // Keep activeProfile in sync if it was renamed/updated server-side, or
    // null it out if the row got deleted elsewhere (e.g., another tab).
    if (activeProfile.value) {
      const updated = profiles.value.find(p => p.id === activeProfile.value!.id)
      syncActiveProfile(updated ?? null)
    }
  } catch (e) {
    ElMessage.error(`載入失敗：${(e as Error).message}`)
  } finally {
    loading.value = false
  }
}

watch(visible, (now) => {
  if (now) refresh()
  else cancelRename()
})

// --- Create ---
const openCreateDialog = () => {
  if (isEditingInventory.value) {
    ElMessage.warning('請先儲存或取消庫存編輯')
    return
  }
  createName.value = ''
  createAsDefault.value = profiles.value.length === 0  // first profile auto-default
  createDialogVisible.value = true
}

const submitCreate = async () => {
  const name = createName.value.trim()
  if (!name) {
    ElMessage.warning('名稱不可為空')
    return
  }
  createSaving.value = true
  try {
    const { inv_h, inv_s } = currentInventoryAsJP()
    const created = await createProfile({ name, inv_h, inv_s })
    // Two-step default toggle is a separate round-trip that can fail
    // independently. If it does, the profile still exists — surface a warning
    // rather than the generic 儲存失敗 (which would imply nothing was saved).
    let defaultMarkFailed = false
    if (createAsDefault.value) {
      try {
        await setDefaultProfile(created.id)
      } catch (e) {
        defaultMarkFailed = true
        console.warn('[profiles] setDefault after create failed:', e)
      }
    }
    createDialogVisible.value = false
    if (defaultMarkFailed) {
      ElMessage.warning(`「${name}」已儲存，但設為預設失敗，請手動點擊星號`)
    } else {
      ElMessage.success(`「${name}」已儲存`)
    }
    refresh()
  } catch (e) {
    ElMessage.error(`儲存失敗：${(e as Error).message}`)
  } finally {
    createSaving.value = false
  }
}

// --- Apply / Overwrite / Delete / Default ---
const onApplyClick = async (p: Profile) => {
  if (isEditingInventory.value) {
    ElMessage.warning('請先儲存或取消庫存編輯')
    return
  }
  // Confirm only when there's actual data at risk — i.e. inventory is
  // non-empty AND we're not just re-applying the already-active profile (a
  // re-apply is harmless). An empty inventory has nothing to lose, so the
  // confirm would just be friction.
  const wouldOverwriteData = activeProfileId.value !== p.id &&
    (ownedHeroes.value.length > 0 || ownedSkills.value.length > 0)
  if (wouldOverwriteData) {
    try {
      await ElMessageBox.confirm(
        `將以「${p.name}」覆寫目前庫存（${p.inv_h.length} 武將, ${p.inv_s.length} 戰法）？目前庫存若未儲存為配置會遺失。`,
        '套用配置',
        { confirmButtonText: '套用', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }
  applyProfile(p)
  ElMessage.success(`已套用「${p.name}」`)
  visible.value = false
}

const overwriteWithCurrent = async (p: Profile) => {
  if (isEditingInventory.value) {
    ElMessage.warning('請先儲存或取消庫存編輯')
    return
  }
  try {
    await ElMessageBox.confirm(
      `用目前庫存（${ownedHeroes.value.length} 武將, ${ownedSkills.value.length} 戰法）覆寫「${p.name}」？`,
      '覆寫配置',
      { confirmButtonText: '覆寫', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const { inv_h, inv_s } = currentInventoryAsJP()
    await updateProfileInventory(p.id, inv_h, inv_s)
    ElMessage.success(`已更新「${p.name}」`)
    refresh()
  } catch (e) {
    ElMessage.error(`更新失敗：${(e as Error).message}`)
  }
}

const removeProfile = async (p: Profile) => {
  try {
    await deleteProfile(p.id)
    profiles.value = profiles.value.filter(x => x.id !== p.id)
    if (activeProfile.value?.id === p.id) syncActiveProfile(null)
    ElMessage.success('已刪除')
  } catch (e) {
    ElMessage.error(`刪除失敗：${(e as Error).message}`)
  }
}

const toggleDefault = async (p: Profile) => {
  try {
    await setDefaultProfile(p.is_default ? null : p.id)
    refresh()
  } catch (e) {
    ElMessage.error(`設定失敗：${(e as Error).message}`)
  }
}

// --- Rename ---
const startRename = (p: Profile) => {
  editingId.value = p.id
  editingDraft.value = p.name
}
const cancelRename = () => {
  editingId.value = null
  editingDraft.value = ''
}
const saveRename = async (p: Profile) => {
  const next = editingDraft.value.trim()
  if (!next) {
    ElMessage.warning('名稱不可為空')
    return
  }
  if (next === p.name) {
    cancelRename()
    return
  }
  try {
    await renameProfile(p.id, next)
    p.name = next
    p.updated_at = new Date().toISOString()
    if (activeProfile.value?.id === p.id) syncActiveProfile({ ...p })
    cancelRename()
    ElMessage.success('已更新')
  } catch (e) {
    ElMessage.error(`更新失敗：${(e as Error).message}`)
  }
}

// --- Import from share link ---
const openImportDialog = () => {
  if (isEditingInventory.value) {
    ElMessage.warning('請先儲存或取消庫存編輯')
    return
  }
  importUrl.value = ''
  importName.value = ''
  importDialogVisible.value = true
}

// Accept either a full URL or just the hash payload. Strips a leading `/`
// in case the user copied a router-normalized URL.
const parseShareInput = (input: string): { slug?: string; base64?: string } => {
  let payload = input.trim()
  const hashIdx = payload.indexOf('#')
  if (hashIdx >= 0) payload = payload.slice(hashIdx + 1)
  payload = payload.replace(/^\//, '')
  if (!payload) throw new Error('連結為空')
  if (payload.startsWith('s/')) return { slug: payload.slice(2) }
  return { base64: payload }
}

interface ShareBlobLike {
  inv_h?: unknown
  inv_s?: unknown
  inventory?: unknown   // legacy v1 — heroes only
}

const submitImport = async () => {
  const url = importUrl.value.trim()
  const name = importName.value.trim()
  if (!url) {
    ElMessage.warning('請貼上分享連結')
    return
  }
  if (!name) {
    ElMessage.warning('請為配置取名')
    return
  }
  importLoading.value = true
  try {
    const parsed = parseShareInput(url)
    let blob: ShareBlobLike
    if (parsed.slug) {
      blob = (await loadShare(parsed.slug)) as ShareBlobLike
    } else {
      const json = decodeURIComponent(escape(atob(parsed.base64!)))
      blob = JSON.parse(json) as ShareBlobLike
    }
    const inv_h = Array.isArray(blob.inv_h) ? blob.inv_h.filter((x): x is string => typeof x === 'string')
      : Array.isArray(blob.inventory) ? blob.inventory.filter((x): x is string => typeof x === 'string')
      : []
    const inv_s = Array.isArray(blob.inv_s) ? blob.inv_s.filter((x): x is string => typeof x === 'string') : []
    if (inv_h.length === 0 && inv_s.length === 0) {
      throw new Error('連結中沒有庫存資料')
    }
    await createProfile({ name, inv_h, inv_s })
    importDialogVisible.value = false
    ElMessage.success(`已匯入「${name}」（${inv_h.length} 武將, ${inv_s.length} 戰法）`)
    refresh()
  } catch (e) {
    ElMessage.error(`匯入失敗：${(e as Error).message}`)
  } finally {
    importLoading.value = false
  }
}

// --- Time helper (matches LineupBuilder.relativeTime) ---
const relativeTime = (iso: string): string => {
  const sec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (sec < 60) return '剛剛'
  if (sec < 3600) return `${Math.floor(sec / 60)} 分鐘前`
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小時前`
  if (sec < 86400 * 30) return `${Math.floor(sec / 86400)} 天前`
  return new Date(iso).toLocaleDateString('zh-Hant')
}
</script>

<style scoped>
/* Default star toggle — identical visual vocab to MyShares' pin star, but
   amber-on means "default profile" rather than "pinned". */
.default-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: #cbd5e1;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.default-btn:hover {
  background: #f1f5f9;
  color: #94a3b8;
}
.default-btn-on,
.default-btn-on:hover {
  color: #f59e0b;
}
.default-btn-on:hover {
  background: #fef3c7;
}
</style>
