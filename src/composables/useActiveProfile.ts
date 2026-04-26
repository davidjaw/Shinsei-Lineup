import { ref, computed, readonly } from 'vue'
import type { Profile } from '../lib/profiles'
import { useInventory } from './useInventory'
import { useData, type Hero, type Skill } from './useData'

// The currently-applied profile (or null if user has never applied one this
// session). Module-level so the dropdown header in LineupBuilder and the
// dialog's apply/sync actions share a single reactive source.
//
// NOT persisted across reloads — applying the default profile on each load is
// the user-visible "remember my profile" mechanism, not a localStorage cache.
const activeProfile = ref<Profile | null>(null)

export function useActiveProfile() {
  const { ownedHeroes, ownedSkills, showOwnedOnly } = useInventory()
  const { heroes, skills } = useData()

  const findHero = (key: string): Hero | undefined =>
    heroes.value.find(h => h.name_jp === key || h.name === key)
  const findSkill = (key: string): Skill | undefined =>
    skills.value.find(s => s.name_jp === key || s.name === key)

  // Replaces the current inventory with the profile's contents AND marks it
  // active. Unknown JP keys (renamed/removed heroes) are silently dropped —
  // same behavior as restoreFromBlob in LineupBuilder.
  const applyProfile = (p: Profile): void => {
    ownedHeroes.value = p.inv_h
      .map(k => findHero(k)?.name)
      .filter((n): n is string => !!n)
    ownedSkills.value = p.inv_s
      .map(k => findSkill(k)?.name)
      .filter((n): n is string => !!n)
    showOwnedOnly.value = ownedHeroes.value.length > 0 || ownedSkills.value.length > 0
    activeProfile.value = p
  }

  // Updates the active profile's metadata WITHOUT touching inventory state.
  // Used when the underlying row was renamed or refreshed from the server but
  // the user hasn't re-applied. Pass null to clear (e.g., active row was
  // deleted). For sign-out, prefer the named clearActiveProfile() — the intent
  // reads better at the call site.
  const syncActiveProfile = (p: Profile | null): void => { activeProfile.value = p }

  const clearActiveProfile = (): void => { activeProfile.value = null }

  return {
    activeProfile: readonly(activeProfile),
    activeProfileName: computed(() => activeProfile.value?.name ?? null),
    activeProfileId: computed(() => activeProfile.value?.id ?? null),
    applyProfile,
    syncActiveProfile,
    clearActiveProfile,
  }
}
