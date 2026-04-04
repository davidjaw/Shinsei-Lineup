import { ref } from 'vue'

// State
const ownedHeros = ref<string[]>([])
const ownedSkills = ref<string[]>([])
const showOwnedOnly = ref(false)

const isEditingInventory = ref(false)
const tempOwnedHeros = ref<string[]>([])
const tempOwnedSkills = ref<string[]>([])

// Actions
const startEditingInventory = () => {
  tempOwnedHeros.value = [...ownedHeros.value]
  tempOwnedSkills.value = [...ownedSkills.value]
  isEditingInventory.value = true
}

const saveInventory = () => {
  ownedHeros.value = [...tempOwnedHeros.value]
  ownedSkills.value = [...tempOwnedSkills.value]
  isEditingInventory.value = false
}

const cancelEditingInventory = () => {
  isEditingInventory.value = false
}

const clearInventory = () => {
  ownedHeros.value = []
  ownedSkills.value = []
}

export function useInventory() {
  return {
    ownedHeros,
    ownedSkills,
    showOwnedOnly,
    isEditingInventory,
    tempOwnedHeros,
    tempOwnedSkills,
    startEditingInventory,
    saveInventory,
    cancelEditingInventory,
    clearInventory
  }
}
