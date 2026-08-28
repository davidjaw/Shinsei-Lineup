import { ref, watch } from 'vue'
import { useProfiles } from './useProfiles'

const CATALOG_MODE_KEY = 'nobunaga.catalogMode'

const readStoredCatalogMode = (): boolean => {
  try {
    return localStorage.getItem(CATALOG_MODE_KEY) === 'inventory'
  } catch {
    return false
  }
}

// State
const ownedHeroes = ref<string[]>([])
const ownedSkills = ref<string[]>([])
const showOwnedOnly = ref(readStoredCatalogMode())

const isEditingInventory = ref(false)
const isCompactView = ref(false)
const tempOwnedHeroes = ref<string[]>([])
const tempOwnedSkills = ref<string[]>([])

watch(showOwnedOnly, (ownedOnly) => {
  try {
    localStorage.setItem(CATALOG_MODE_KEY, ownedOnly ? 'inventory' : 'free')
  } catch {
    // localStorage may be unavailable (private mode / quota).
  }
})

// Actions
const startEditingInventory = () => {
  tempOwnedHeroes.value = [...ownedHeroes.value]
  tempOwnedSkills.value = [...ownedSkills.value]
  isEditingInventory.value = true
  isCompactView.value = false
}

const saveInventory = () => {
  ownedHeroes.value = [...tempOwnedHeroes.value]
  ownedSkills.value = [...tempOwnedSkills.value]
  isEditingInventory.value = false
  // Manual save = explicit user intent. Block tryAutoApplyDefault from
  // overwriting on a still-pending session resolution.
  useProfiles().markUserTouched()
}

const cancelEditingInventory = () => {
  isEditingInventory.value = false
}

const clearInventory = () => {
  ownedHeroes.value = []
  ownedSkills.value = []
}

export function useInventory() {
  return {
    ownedHeroes,
    ownedSkills,
    showOwnedOnly,
    isEditingInventory,
    isCompactView,
    tempOwnedHeroes,
    tempOwnedSkills,
    startEditingInventory,
    saveInventory,
    cancelEditingInventory,
    clearInventory
  }
}
