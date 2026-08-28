<template>
  <div class="flex h-dvh w-full bg-white text-ink">
    <AppSidebar
      v-model:collapsed="sidebarCollapsed"
      v-model:mobileOpen="sidebarMobileOpen"
    />
    <main class="flex-1 min-w-0 flex flex-col overflow-hidden">
      <LineupHeader
        v-if="route.name === 'lineup'"
        v-model:team-name="currentTeamName"
        :total-cost="totalCost"
        :troop-levels="troopLevels"
        :is-editing-inventory="isEditingInventory"
        :is-logged-in="isLoggedIn"
        :has-unseen-changelog="hasUnseenChangelog"
        :display-name="displayName"
        :active-profile-name="activeProfileName"
        @open-mobile-sidebar="dialogs.open('mobile-team-drawer')"
        @start-editing-inventory="startEditingInventory"
        @cancel-editing-inventory="cancelEditingInventory"
        @save-inventory="saveInventory"
        @save-inventory-active="onSaveInventoryToActive"
        @save-inventory-new="onSaveInventoryToNew"
        @open-share="dialogs.open('share')"
        @open-reset="dialogs.open('reset')"
        @open-changelog="dialogs.open('changelog')"
        @open-auth="dialogs.open('auth')"
        @user-menu="onUserMenu"
        @apply-profile="onApplyProfile"
        @unload-profile="onUnloadProfile"
        @goto-profiles="router.push({ name: 'profiles' })"
        @import-from-link="dialogs.open('import-from-link')"
      />
      <PageHeader
        v-else
        :title="pageTitle"
        :description="pageDescription"
        :is-logged-in="isLoggedIn"
        :display-name="displayName"
        :has-unseen-changelog="hasUnseenChangelog"
        @open-mobile-sidebar="sidebarMobileOpen = true"
        @open-changelog="dialogs.open('changelog')"
        @open-auth="dialogs.open('auth')"
        @user-menu="onUserMenu"
      />
      <router-view />
    </main>

    <!-- User display-name rename dialog. Lives at the layout level so it's
         reachable from every page's UserControls menu, not just the lineup
         route. -->
    <RenameDialog
      v-model="renameDialogVisible"
      v-model:name="renameInput"
      :saving="renameSaving"
      @submit="submitRename"
    />

    <!-- Cloud-sync dialogs (Phase C). Live at the layout level so they
         surface regardless of which route the user is on when a merge /
         conflict needs resolving. -->
    <MergeOnSignInDialog />
    <CloudConflictDialog />

    <!-- Auth + changelog dialogs. Layout-level so login / 更新紀錄 work
         from every route, not just the lineup builder. -->
    <ChangelogDialog v-model="changelogDialogVisible" />
    <AuthDialog v-model="authDialogVisible" @sign-in="onSignIn" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppSidebar from '../components/layout/AppSidebar.vue'
import LineupHeader from '../components/lineup-builder/LineupHeader.vue'
import PageHeader from '../components/layout/PageHeader.vue'
import RenameDialog from '../components/dialogs/RenameDialog.vue'
import MergeOnSignInDialog from '../components/dialogs/MergeOnSignInDialog.vue'
import CloudConflictDialog from '../components/dialogs/CloudConflictDialog.vue'
import ChangelogDialog from '../components/dialogs/ChangelogDialog.vue'
import AuthDialog from '../components/dialogs/AuthDialog.vue'
import type { UserMenuCmd } from '../components/layout/UserControls.vue'
import { useLineups } from '../composables/useLineups'
import { useInventory } from '../composables/useInventory'
import { useTroopLevels } from '../composables/useTroopLevels'
import { useAuth } from '../composables/useAuth'
import { useActiveProfile } from '../composables/useActiveProfile'
import { useProfiles } from '../composables/useProfiles'
import { useDialogs } from '../composables/useDialogs'
import { useChangelog } from '../composables/useChangelog'
import { useData } from '../composables/useData'
import { useGroupPersistence } from '../composables/useGroupPersistence'
import { makeSerializer } from '../lib/lineupSerialize'
import {
  createProfile, updateProfileInventory, type Profile,
} from '../lib/profiles'

const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)
const sidebarMobileOpen = ref(false)

// Title / description for the shared PageHeader. Routes declare these
// statically via meta; the coming-soon page picks dynamic values per :topic.
const COMING_SOON_META: Record<string, { title: string; description: string }> = {
  'battle-sim': {
    title: '戰鬥模擬',
    description: '依照雙方陣容自動推演戰鬥流程；老實說目前八字沒半撇，先別期待。',
  },
  'hero-db': {
    title: '武將資料庫',
    description: '橫向比較各武將屬性、適性與「精選隊伍」上的人氣度；不做配置建議，純資料呈現。目前仍在開發中。',
  },
}
const pageTitle = computed<string>(() => {
  if (route.name === 'comingSoon') {
    const topic = String(route.params.topic ?? '')
    return COMING_SOON_META[topic]?.title ?? '即將推出'
  }
  return String(route.meta.title ?? route.name ?? '')
})
const pageDescription = computed<string | undefined>(() => {
  if (route.name === 'comingSoon') {
    const topic = String(route.params.topic ?? '')
    return COMING_SOON_META[topic]?.description ?? '此功能尚未上線。'
  }
  const d = route.meta.description
  return typeof d === 'string' ? d : undefined
})

const { currentLineup, currentTeamName, totalCost } = useLineups()
const troopLevels = useTroopLevels(currentLineup)
const {
  isEditingInventory,
  isCompactView,
  startEditingInventory,
  cancelEditingInventory,
  saveInventory,
  ownedHeroes,
  ownedSkills,
} = useInventory()

watch(() => route.name, (name) => {
  if (name !== 'lineup') isCompactView.value = false
})

const { isLoggedIn, displayName, signIn, signOut, updateDisplayName } = useAuth()
const {
  activeProfile, activeProfileName, applyProfile, unloadProfile, syncActiveProfile, clearActiveProfile,
} = useActiveProfile()
const { profiles, refresh: refreshProfiles } = useProfiles()
const dialogs = useDialogs()
const { hasUnseen: hasUnseenChangelog, changelogDialogVisible } = useChangelog()
const { heroes, skills } = useData()
const { flushPendingCloudPush, flushLocalAutosave, snapshotForRecovery } = useGroupPersistence()

const authDialogVisible = dialogs.useDialog('auth')

// OAuth full-page redirect — snapshot in-progress lineup so the post-redirect
// mount can restore it. Snapshot itself is harmless from non-lineup routes
// (it just captures the current state, which on those routes is whatever
// the user last had in the builder).
const onSignIn = (provider: Parameters<typeof signIn>[0]) => {
  authDialogVisible.value = false
  snapshotForRecovery()
  signIn(provider)
}

// CHT→JP name lookup so saved profiles stay translation-stable. Uses the
// shared serializer factory (which also handles aliases) so the mapping
// rules stay in one place — see lineupSerialize.ts.
const serializer = computed(() =>
  makeSerializer({ heroes: heroes.value, skills: skills.value }),
)
const inventoryAsJP = (h: string[], s: string[]): { inv_h: string[]; inv_s: string[] } => ({
  inv_h: h.map(n => serializer.value.toJpHero(n) ?? n),
  inv_s: s.map(n => serializer.value.toJpSkill(n) ?? n),
})

const onApplyProfile = (id: string) => {
  if (isEditingInventory.value) {
    ElMessage.warning('請先儲存或取消庫存編輯')
    return
  }
  const p = profiles.value.find(x => x.id === id)
  if (!p) {
    ElMessage.error('找不到該角色配置，請重新整理頁面')
    return
  }
  applyProfile(p)
  ElMessage.success(`已套用「${p.name}」`)
}

const onUnloadProfile = () => {
  if (isEditingInventory.value) {
    ElMessage.warning('請先儲存或取消庫存編輯')
    return
  }
  unloadProfile()
  ElMessage.info('已切換為不使用任何角色配置')
}

// Commit the temp inventory to the active profile. saveInventory() copies
// temp → owned*, then we PATCH the row and re-sync local activeProfile so the
// pill / panel show the new counts immediately.
const onSaveInventoryToActive = async () => {
  const active = activeProfile.value
  if (!active) {
    ElMessage.error('沒有作用中的角色配置')
    return
  }
  saveInventory()
  try {
    const { inv_h, inv_s } = inventoryAsJP(ownedHeroes.value, ownedSkills.value)
    await updateProfileInventory(active.id, inv_h, inv_s)
    syncActiveProfile({ ...active, inv_h, inv_s, updated_at: new Date().toISOString() })
    void refreshProfiles().catch(() => { /* swallow */ })
    ElMessage.success(`已更新「${active.name}」`)
  } catch (e) {
    ElMessage.error(`儲存失敗：${(e as Error).message}`)
  }
}

// Save current edits as a new profile and switch to it. saveInventory()
// commits the temp first; createProfile uses the freshly committed inventory.
const onSaveInventoryToNew = async (name: string) => {
  saveInventory()
  try {
    const { inv_h, inv_s } = inventoryAsJP(ownedHeroes.value, ownedSkills.value)
    const created: Profile = await createProfile({ name, inv_h, inv_s })
    applyProfile(created)
    void refreshProfiles().catch(() => { /* swallow */ })
    ElMessage.success(`已建立並切換到「${name}」`)
  } catch (e) {
    ElMessage.error(`建立失敗：${(e as Error).message}`)
  }
}

const renameDialogVisible = dialogs.useDialog('rename')
const renameInput = ref('')
const renameSaving = ref(false)
watch(renameDialogVisible, (now) => {
  if (now) renameInput.value = displayName.value ?? ''
})
const submitRename = async () => {
  const name = renameInput.value.trim()
  if (!name) {
    ElMessage.warning('名稱不可為空')
    return
  }
  renameSaving.value = true
  try {
    await updateDisplayName(name)
    renameDialogVisible.value = false
    ElMessage.success('名稱已更新')
  } catch (e) {
    ElMessage.error(`更新失敗：${(e as Error).message}`)
  } finally {
    renameSaving.value = false
  }
}

const onUserMenu = async (cmd: UserMenuCmd) => {
  if (cmd === 'signout') {
    // Flush local FIRST (synchronous): the user's in-flight edits made within
    // ~800ms of clicking logout sit in the debounced autosave timer and would
    // otherwise be lost when the page transitions / reloads after signout.
    // Then flush cloud (async) so any pending push completes before the auth
    // token is invalidated.
    flushLocalAutosave()
    await flushPendingCloudPush()
    await signOut()
    clearActiveProfile()
    ElMessage.success('已登出')
  } else if (cmd === 'rename') {
    dialogs.open('rename')
  } else if (cmd === 'changelog') {
    dialogs.open('changelog')
  }
}
</script>
