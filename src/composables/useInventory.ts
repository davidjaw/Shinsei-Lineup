import { ref } from 'vue'

// State
const ownedHeroes = ref<string[]>([])
const ownedSkills = ref<string[]>([])
const showOwnedOnly = ref(false)

const isEditingInventory = ref(false)
const tempOwnedHeroes = ref<string[]>([])
const tempOwnedSkills = ref<string[]>([])

// Actions
const startEditingInventory = () => {
  tempOwnedHeroes.value = [...ownedHeroes.value]
  tempOwnedSkills.value = [...ownedSkills.value]
  isEditingInventory.value = true
}

const saveInventory = () => {
  ownedHeroes.value = [...tempOwnedHeroes.value]
  ownedSkills.value = [...tempOwnedSkills.value]
  isEditingInventory.value = false
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
    tempOwnedHeroes,
    tempOwnedSkills,
    startEditingInventory,
    saveInventory,
    cancelEditingInventory,
    clearInventory
  }
}
