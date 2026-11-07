import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, type App } from 'vue'
import type { CloudLineupGroup } from '../../lib/lineupGroups'
import type { LocalOwner } from '../../composables/useGroupPersistence'

vi.mock('../../lib/bans', () => ({ fetchMyBan: async () => false }))

// Only this dialog's own markup: element-plus rendering is not what is under test.
const ElDialog = defineComponent({
  props: { modelValue: Boolean },
  setup: (props, { slots }) => () => (props.modelValue ? h('div', [slots.default?.(), slots.footer?.()]) : null),
})
const ElButton = defineComponent({
  props: { disabled: Boolean },
  setup: (props, { slots }) => () => h('button', { disabled: props.disabled }, slots.default?.()),
})

const cloudRow = (name = '雲端編組', updated_at = 't0'): CloudLineupGroup =>
  ({ id: 'r9', client_id: 'f_g_9', name, teams: [{ name: 't', m: 'x' }], sort_order: 0, updated_at }) as unknown as CloudLineupGroup

let app: App | null = null

const mount = async (localOwner: LocalOwner, cloudRows: CloudLineupGroup[]) => {
  vi.resetModules()
  const persistence = (await import('../../composables/useGroupPersistence')).useGroupPersistence()
  const { default: Dialog } = await import('./MergeOnSignInDialog.vue')
  persistence.cloudMerge.value = { localBlob: { v: 5, workspaces: { free: { groups: [] }, inventory: { groups: [] } } }, cloudRows, localOwner }
  const root = document.createElement('div')
  app = createApp(Dialog)
  app.component('ElDialog', ElDialog)
  app.component('ElButton', ElButton)
  app.mount(root)
  await nextTick()
  const titles = () => [...root.querySelectorAll('.option-card__title')].map((el) => el.textContent)
  const selected = () => root.querySelector('.option-card--active .option-card__title')?.textContent ?? null
  const confirm = () => [...root.querySelectorAll('button')].find((b) => b.textContent === '確認')!
  const later = () => [...root.querySelectorAll('button')].find((b) => b.textContent === '稍後再決定')!
  const pick = async (title: string) => {
    const card = [...root.querySelectorAll('.option-card')].find((el) => el.textContent?.includes(title))!
    card.querySelector('input')!.dispatchEvent(new Event('change'))
    await nextTick()
  }
  return { root, persistence, titles, selected, confirm, later, pick }
}

const KEEP_CLOUD = '採用帳號之前保存的編組'
const KEEP_LOCAL = '採用這台裝置目前的編組'
const APPEND = '兩邊都保留'

beforeEach(() => localStorage.clear())
afterEach(() => {
  app?.unmount()
  app = null
})

describe('what the dialog opens with', () => {
  it.each([
    ['other', 'empty', [], null, true, true],
    ['other', 'non-empty', [cloudRow()], KEEP_CLOUD, false, true],
    ['unknown', 'empty', [], null, true, false],
    ['unknown', 'non-empty', [cloudRow()], null, true, false],
    ['this', 'empty', [], APPEND, false, false],
    ['this', 'non-empty', [cloudRow()], APPEND, false, false],
  ] as const)('owner %s, %s cloud', async (owner, _cloud, rows, selected, disabled, saysOther) => {
    const dialog = await mount(owner, [...rows])
    if (selected) expect(dialog.selected()).toContain(selected)
    else expect(dialog.selected()).toBeNull()
    expect(dialog.confirm().disabled).toBe(disabled)
    expect(dialog.later().disabled).toBe(false)
    expect(dialog.root.textContent!.includes('其他帳號')).toBe(saysOther)
    expect(dialog.titles().some((t) => t?.includes(KEEP_CLOUD))).toBe(rows.length > 0)
  })

  it('enables 確認 once a pick is made', async () => {
    const dialog = await mount('unknown', [cloudRow()])
    await dialog.pick(KEEP_LOCAL)
    expect(dialog.selected()).toContain(KEEP_LOCAL)
    expect(dialog.confirm().disabled).toBe(false)
  })

  it('shows nothing once the prompt closes', async () => {
    const dialog = await mount('this', [cloudRow()])
    dialog.persistence.cloudMerge.value = null
    await nextTick()
    expect(dialog.root.querySelector('.option-card')).toBeNull()
  })
})

describe('rows changing under an open dialog', () => {
  it("keeps the user's keep-local when another account's dialog would preselect keep-cloud", async () => {
    const dialog = await mount('other', [cloudRow()])
    await dialog.pick(KEEP_LOCAL)
    dialog.persistence.cloudMerge.value!.cloudRows = [cloudRow('別處改過', 't1')]
    await nextTick()
    expect(dialog.selected()).toContain(KEEP_LOCAL)
  })

  it('does not turn a keep-local made over an empty cloud into keep-cloud when rows arrive', async () => {
    const dialog = await mount('other', [])
    await dialog.pick(KEEP_LOCAL)
    dialog.persistence.cloudMerge.value!.cloudRows = [cloudRow()]
    await nextTick()
    expect(dialog.selected()).toContain(KEEP_LOCAL)
  })

  it('keeps the choice when the cloud empties and it is still offered', async () => {
    const dialog = await mount('other', [cloudRow()])
    await dialog.pick(KEEP_LOCAL)
    dialog.persistence.cloudMerge.value!.cloudRows = []
    await nextTick()
    expect(dialog.selected()).toContain(KEEP_LOCAL)
  })

  it('drops a choice no longer offered, to the default for the owner', async () => {
    const dialog = await mount('this', [cloudRow()])
    await dialog.pick(KEEP_CLOUD)
    dialog.persistence.cloudMerge.value!.cloudRows = []
    await nextTick()
    expect(dialog.selected()).toContain(APPEND)
  })

  it('takes no side for a preselected keep-cloud when the cloud empties', async () => {
    const dialog = await mount('other', [cloudRow()])
    expect(dialog.selected()).toContain(KEEP_CLOUD)
    dialog.persistence.cloudMerge.value!.cloudRows = []
    await nextTick()
    expect(dialog.selected()).toBeNull()
    expect(dialog.confirm().disabled).toBe(true)
  })

  it("preselects keep-cloud for a known other account's prompt when rows arrive and nothing was picked", async () => {
    const dialog = await mount('other', [])
    expect(dialog.selected()).toBeNull()
    dialog.persistence.cloudMerge.value!.cloudRows = [cloudRow()]
    await nextTick()
    expect(dialog.selected()).toContain(KEEP_CLOUD)
  })
})
