// The season control over a restored group: a switch that would leave something out asks once, listing the names
// and the count, with three answers (remove and switch, keep and switch, cancel); one that leaves nothing out just
// switches; 移除非本賽季 lists what goes before it goes. The inventory is never touched. Element Plus is stubbed.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, h, nextTick, type App } from 'vue'
import type { ShareableData } from '../../constants/gameData'

vi.mock('../../lib/bans', () => ({ fetchMyBan: async () => false }))

const Passthrough = defineComponent({ setup: (_, { slots }) => () => h('div', Object.values(slots).map((slot) => slot?.())) })
const ElDialog = defineComponent({
  props: { modelValue: Boolean },
  setup: (props, { slots }) => () => (props.modelValue ? h('div', { class: 'dialog' }, [slots.default?.(), slots.footer?.()]) : null),
})
const ElButton = defineComponent({ setup: (_, { slots }) => () => h('button', slots.default?.()) })
const ElDropdown = defineComponent({
  emits: ['command'],
  setup: (_, { slots, emit }) => () => h('div', {
    onClick: (e: Event) => {
      const command = (e.target as HTMLElement).closest('[data-command]')?.getAttribute('data-command')
      if (command) emit('command', command)
    },
  }, [slots.default?.(), slots.dropdown?.()]),
})
const ElDropdownItem = defineComponent({ props: { command: String }, setup: (props, { slots }) => () => h('button', { 'data-command': props.command }, slots.default?.()) })

// 伊達政宗 PK with 疑兵盜城 S2; 織田信長 S1 with 龍騎兵 PK and 合盟之陣 S3; 阿江 with 追亡逐北 PK. A second group
// holds only S1.
const seed = (season: string): void => {
  const blob = {
    v: 5,
    inv_h: ['伊達政宗'],
    inv_s: ['城盗り'],
    workspaces: {
      free: { active_group_index: 0, groups: [
        { id: 'f_g_1', name: '主力', teams: [{ name: '混合隊', m: '伊達政宗', m_s1: '城盗り', v1: '織田信長', v1_s1: '竜騎兵', v1_s2: '会盟の陣', v2: 'お江', v2_s1: '追い崩し' }] },
        { id: 'f_g_2', name: '純 S1', teams: [{ name: '一隊', m: '織田信長' }] },
      ] },
      inventory: { groups: [] },
    },
  } as unknown as ShareableData
  localStorage.setItem('nobunaga.groups.v5', JSON.stringify(blob))
  localStorage.setItem('nobunaga.gameSeason', season)
}

let app: App | null = null
const openChannels: BroadcastChannel[] = []
const RealChannel = BroadcastChannel

beforeEach(() => {
  vi.stubGlobal('BroadcastChannel', class extends RealChannel {
    constructor(name: string) {
      super(name)
      openChannels.push(this)
    }
  })
  localStorage.clear()
})
afterEach(() => {
  app?.unmount()
  app = null
  vi.unstubAllGlobals()
  openChannels.splice(0).forEach((channel) => channel.close())
})

const mount = async (season: string) => {
  seed(season)
  vi.resetModules()
  const persistence = (await import('../../composables/useGroupPersistence')).useGroupPersistence()
  persistence.restoreFromLocalStorage()
  const { default: Control } = await import('./GameSeasonControl.vue')
  const state = (await import('../../composables/useGameSeason')).useGameSeason()
  const { lineups } = (await import('../../composables/useLineups')).useLineups()
  const inventory = (await import('../../composables/useInventory')).useInventory()
  const groups = (await import('../../composables/useGroups')).useGroups()
  const root = document.createElement('div')
  app = createApp(Control)
  for (const [name, stub] of Object.entries({ ElDialog, ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu: Passthrough, ElIcon: Passthrough })) app.component(name, stub)
  app.mount(root)
  await nextTick()
  const byId = (id: string) => root.querySelector<HTMLElement>(`[data-testid="${id}"]`)
  const click = async (el: HTMLElement | null | undefined) => {
    el!.click()
    await nextTick()
  }
  const button = (label: string) => [...root.querySelectorAll<HTMLElement>('.dialog button')].find((b) => b.textContent === label)
  const heroesOnTeam = () => [lineups[0].main.hero?.name ?? null, lineups[0].vice1.hero?.name ?? null, lineups[0].vice2.hero?.name ?? null]
  return { root, byId, click, button, state, lineups, inventory, groups, heroesOnTeam, pick: (s: string) => click(root.querySelector<HTMLElement>(`[data-command="${s}"]`)) }
}

describe('switching to a season that leaves something out', () => {
  it('asks once, naming each item and the count', async () => {
    const page = await mount('PK')
    expect(page.byId('game-season-value')?.textContent).toBe('PK')
    expect(page.byId('game-season-clear')).toBeNull()
    await page.pick('S1')
    expect(page.root.querySelectorAll('.dialog')).toHaveLength(1)
    expect(page.byId('game-season-switch-dialog')?.textContent).toContain('目前編組「主力」有 5 項 S1 沒有')
    expect(page.byId('game-season-switch-names')?.textContent).toBe('伊達政宗、疑兵盜城、龍騎兵、合盟之陣、追亡逐北')
  })

  it('cancel: nothing changes', async () => {
    const page = await mount('PK')
    await page.pick('S1')
    await page.click(page.button('取消'))
    expect(page.root.querySelector('.dialog')).toBeNull()
    expect(page.state.gameSeason.value).toBe('PK')
    expect(page.heroesOnTeam()).toEqual(['伊達政宗', '織田信長', '阿江'])
  })

  it('keep and switch: everything stays, marked, and 移除非本賽季 appears', async () => {
    const page = await mount('PK')
    await page.pick('S2')
    await page.click(page.button('保留並切換'))
    expect(page.state.gameSeason.value).toBe('S2')
    expect(page.byId('game-season-value')?.textContent).toBe('S2')
    expect(page.heroesOnTeam()).toEqual(['伊達政宗', '織田信長', '阿江'])
    expect(page.state.misfits.value.map((m) => m.name)).toEqual(['伊達政宗', '龍騎兵', '合盟之陣', '追亡逐北'])
    expect(page.byId('game-season-badge')?.textContent).toBe('4')
    expect(page.state.misfitCounts.value).toEqual([4])
    expect(page.byId('game-season-clear')).not.toBeNull()
  })

  it('remove and switch: exactly what the season lacks goes, the inventory stays', async () => {
    const page = await mount('PK')
    await page.pick('S3')
    await page.click(page.button('移除並切換'))
    expect(page.state.gameSeason.value).toBe('S3')
    expect(page.heroesOnTeam()).toEqual([null, '織田信長', '阿江'])
    expect(page.lineups[0].vice1.skill2?.name).toBe('合盟之陣')
    expect(page.state.misfits.value).toEqual([])
    expect(page.inventory.ownedHeroes.value).toEqual(['伊達政宗'])
    expect(page.inventory.ownedSkills.value).toEqual(['疑兵盜城'])
  })
})

describe('switching when nothing would be left out', () => {
  it('just switches, with no dialog', async () => {
    const page = await mount('PK')
    page.groups.setCurrentGroup(1)
    await page.pick('S1')
    expect(page.root.querySelector('.dialog')).toBeNull()
    expect(page.state.gameSeason.value).toBe('S1')
  })

  it('switching group asks nothing: the marks follow the group', async () => {
    const page = await mount('S1')
    expect(page.byId('game-season-clear')).not.toBeNull()
    page.groups.setCurrentGroup(1)
    await nextTick()
    expect(page.root.querySelector('.dialog')).toBeNull()
    expect(page.byId('game-season-clear')).toBeNull()
    expect(page.byId('game-season-badge')).toBeNull()
  })
})

describe('移除非本賽季', () => {
  it('lists the names first, and on 移除 clears them from the active group only', async () => {
    const page = await mount('S1')
    await page.click(page.byId('game-season-clear'))
    expect(page.byId('game-season-clear-dialog')?.textContent).toContain('會從編組「主力」清掉下列 5 項')
    expect(page.byId('game-season-clear-names')?.textContent).toBe('伊達政宗、疑兵盜城、龍騎兵、合盟之陣、追亡逐北')
    await page.click(page.button('移除'))
    expect(page.root.querySelector('.dialog')).toBeNull()
    expect(page.heroesOnTeam()).toEqual([null, '織田信長', '阿江'])
    expect(page.state.misfits.value).toEqual([])
    expect(page.inventory.ownedHeroes.value).toEqual(['伊達政宗'])
    const stored = JSON.parse(localStorage.getItem('nobunaga.groups.v5')!) as ShareableData
    expect(stored.workspaces!.free!.groups![1].teams[0]).toMatchObject({ m: '織田信長' })
  })

  it('cancel keeps everything', async () => {
    const page = await mount('S1')
    await page.click(page.byId('game-season-clear'))
    await page.click(page.button('取消'))
    expect(page.heroesOnTeam()).toEqual(['伊達政宗', '織田信長', '阿江'])
  })
})
