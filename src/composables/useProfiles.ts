import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listMyProfiles, type Profile } from '../lib/profiles'
import { createShare } from '../lib/share'
import { useAuth } from './useAuth'
import { useInventory } from './useInventory'
import { useActiveProfile } from './useActiveProfile'

// Module-level cache shared by the panel, header dropdown, and auto-apply.
// Mutated in-place by inline rename in MyProfilesPanel; call refresh() after
// server-side changes to resync.
const profiles = ref<Profile[]>([])
const loading = ref(false)

// Sticky per-session flag: true once the user has manually applied, unloaded,
// or saved an inventory state. tryAutoApplyDefault bails when set so a manual
// "不使用" click before listMyProfiles resolves doesn't get clobbered.
const userTouchedInventory = ref(false)

const refresh = async (): Promise<void> => {
  const { isLoggedIn } = useAuth()
  if (!isLoggedIn.value) {
    profiles.value = []
    return
  }
  loading.value = true
  try {
    profiles.value = await listMyProfiles()
    const { activeProfile, syncActiveProfile } = useActiveProfile()
    if (activeProfile.value) {
      const updated = profiles.value.find(p => p.id === activeProfile.value!.id)
      syncActiveProfile(updated ?? null)
    }
  } finally {
    loading.value = false
  }
}

const tryAutoApplyDefault = async (): Promise<void> => {
  const { isLoggedIn } = useAuth()
  const { ownedHeroes, ownedSkills } = useInventory()
  const { applyProfile } = useActiveProfile()

  if (!isLoggedIn.value) return
  if (userTouchedInventory.value) return
  if (ownedHeroes.value.length > 0 || ownedSkills.value.length > 0) return

  try {
    if (profiles.value.length === 0) {
      profiles.value = await listMyProfiles()
    }
    // Re-check after the await — the user may have touched inventory while
    // listMyProfiles was in flight.
    if (userTouchedInventory.value) return
    if (ownedHeroes.value.length > 0 || ownedSkills.value.length > 0) return

    const def = profiles.value.find(p => p.is_default)
    if (def) {
      applyProfile(def, { switchToInventory: false })
      ElMessage.info(`已載入預設角色配置：${def.name}`)
    }
  } catch (e) {
    // First-time users without grants/profiles shouldn't see an error toast.
    console.warn('[profiles] auto-load default skipped:', e)
  }
}

const markUserTouched = (): void => {
  userTouchedInventory.value = true
}

const reset = (): void => {
  profiles.value = []
  userTouchedInventory.value = false
  shareSlugCache.clear()
}

// In-session dedup for "share this profile" so spam-clicking doesn't write
// a new shares row each time. Key = profile id; entry tracks the inventory
// fingerprint at the moment of share, so if the user later updates the
// profile's inventory the next share will mint a fresh slug instead of
// pointing recipients at stale data.
const shareSlugCache = new Map<string, { slug: string; fingerprint: string }>()

const fingerprintInventory = (inv_h: string[], inv_s: string[]): string =>
  JSON.stringify({ h: [...inv_h].sort(), s: [...inv_s].sort() })

export const getOrCreateProfileShareSlug = async (p: Profile): Promise<string> => {
  const fp = fingerprintInventory(p.inv_h, p.inv_s)
  const cached = shareSlugCache.get(p.id)
  if (cached && cached.fingerprint === fp) return cached.slug

  const slug = await createShare(
    { inv_h: p.inv_h, inv_s: p.inv_s },
    { kind: 'profile', displayName: `角色配置：${p.name}` },
  )
  shareSlugCache.set(p.id, { slug, fingerprint: fp })
  return slug
}

export function useProfiles() {
  return {
    profiles,
    loading,
    userTouchedInventory,
    refresh,
    tryAutoApplyDefault,
    markUserTouched,
    reset,
  }
}
