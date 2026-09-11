import { ref, computed, type WritableComputedRef } from 'vue'

// Single-active overlay model — at most one dialog or drawer is open at any
// time. Opening a new one replaces the previous, which doubles as
// "auto-close prior" behavior. Drawers (mobile-team) live alongside dialogs
// since they're mutually exclusive overlays from the user's perspective.
export type OverlayName =
  | 'share'
  | 'reset'
  | 'auth'
  | 'rename'
  | 'changelog'
  | 'skill-select'
  | 'mobile-slot-detail'
  | 'mobile-team-drawer'
  | 'create-proposal'
  | 'export-team-to-group'
  | 'import-from-link'
  | 'import-handbook'

  // Note: cloud-merge / cloud-conflict are NOT in this union. Those dialogs
  // are controlled directly by cloudMerge.value / cloudConflict.value refs
  // inside useGroupPersistence so the single-active overlay logic here
  // doesn't interfere with their lifecycle.

const active = ref<OverlayName | null>(null)

const open = (name: OverlayName) => { active.value = name }
const close = () => { active.value = null }

const useDialog = (name: OverlayName): WritableComputedRef<boolean> => computed({
  get: () => active.value === name,
  set: (v: boolean) => { v ? open(name) : (active.value === name && close()) },
})

export function useDialogs() {
  return {
    active,
    open,
    close,
    useDialog,
  }
}
