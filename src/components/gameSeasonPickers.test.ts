// The pickers under a game season: they list only what it offers, in inventory mode only what is owned and offered,
// their filter choices come from that list, and the inventory editor never drops what is owned outside the season.
// A slot marks what the season does not offer. Element Plus is stubbed: its rendering is not what is under test.
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, nextTick, type App, type Component } from 'vue'
import { useData } from '../composables/useData'
import { gameSeasonOffer, offeredHeroes } from '../lib/gameSeasonMisfits'
import HeroLibrary from './HeroLibrary.vue'
import LineupSlot from './LineupSlot.vue'
import SkillLibrary from './SkillLibrary.vue'

/** Renders every slot it gets (default, reference, footer…), so popovers and tooltips show their trigger. */
const Passthrough = defineComponent({ setup: (_, { slots }) => () => h('div', Object.values(slots).map((slot) => slot?.())) })
const ElButton = defineComponent({ setup: (_, { slots }) => () => h('button', slots.default?.()) })
const ElOption = defineComponent({ props: { value: String }, setup: (props) => () => h('option', { class: 'el-option' }, props.value) })
const STUBS: Record<string, Component> = {
  ElInput: Passthrough, ElIcon: Passthrough, ElPopover: Passthrough, ElTooltip: Passthrough, ElSwitch: Passthrough,
  ElDialog: Passthrough, ElSelect: Passthrough, ElOption, ElButton,
}

let app: App | null = null
afterEach(() => {
  app?.unmount()
  app = null
})

const mount = async (component: Component, props: Record<string, unknown>) => {
  const root = document.createElement('div')
  const events: { owned: string[][] } = { owned: [] }
  app = createApp(component, {
    ...props,
    'onUpdate:ownedHeroes': (v: string[]) => events.owned.push(v),
    'onUpdate:ownedSkills': (v: string[]) => events.owned.push(v),
  })
  for (const [name, stub] of Object.entries(STUBS)) app.component(name, stub)
  app.mount(root)
  await nextTick()
  return { root, events }
}

const { heroes, skills } = useData()
const heroNames = (root: Element) => [...root.querySelectorAll('.grid > div')].map((el) => el.textContent?.replace(/\s+/g, ' ').trim() ?? '')
const skillNames = (root: Element) => [...root.querySelectorAll('span.font-bold.text-gray-800')].map((el) => el.textContent)
const chipsOf = (root: Element, row: string) =>
  [...root.querySelectorAll('.flex.items-center, .flex.items-start')]
    .find((el) => el.querySelector('span.w-8')?.textContent === row)
    ?.querySelectorAll('button:not(.font-bold)').length ?? 0

describe('the hero picker', () => {
  it('lists only what the season offers', async () => {
    const { root } = await mount(HeroLibrary, { mode: 'select', gameSeason: 'S1' })
    const names = heroNames(root)
    expect(names).toHaveLength(133)
    expect(names.some((n) => n.includes('伊達政宗'))).toBe(false)
    expect(names.some((n) => n.includes('阿江'))).toBe(true)
  })

  it('in inventory mode lists what is owned and offered: owned ∩ season', async () => {
    const { root } = await mount(HeroLibrary, { mode: 'select', gameSeason: 'S1', filterOwned: true, ownedHeroes: ['伊達政宗', '織田信長', '阿江'] })
    expect(heroNames(root).map((n) => n.match(/織田信長|阿江|伊達政宗/)?.[0])).toEqual(['織田信長', '阿江'])
  })

  it('draws its cost, faction and clan chips from the season\'s heroes', async () => {
    const s1 = offeredHeroes(heroes.value, gameSeasonOffer('S1', heroes.value))
    const { root } = await mount(HeroLibrary, { mode: 'select', gameSeason: 'S1' })
    expect(chipsOf(root, '勢力')).toBe(new Set(s1.map((h) => h.faction)).size)
    expect(chipsOf(root, '家門')).toBe(new Set(s1.map((h) => h.clan).filter(Boolean)).size)
    expect(chipsOf(root, 'Cost')).toBe(new Set(s1.map((h) => h.cost)).size)
    expect(new Set(s1.map((h) => h.clan).filter(Boolean)).size).toBeLessThan(new Set(heroes.value.map((h) => h.clan).filter(Boolean)).size)
  })

  it('without a season (the gacha editor) lists the whole catalog', async () => {
    const { root } = await mount(HeroLibrary, { mode: 'select' })
    expect(heroNames(root)).toHaveLength(heroes.value.length)
  })

  it('in the inventory editor, 全選 adds the season\'s heroes and keeps those owned outside it', async () => {
    const { root, events } = await mount(HeroLibrary, { mode: 'manage', gameSeason: 'S1', ownedHeroes: ['伊達政宗'] })
    const selectAll = [...root.querySelectorAll('button')].find((b) => b.textContent?.trim() === '全選')!
    selectAll.click()
    const [owned] = events.owned
    expect(owned).toContain('伊達政宗')
    expect(owned).toHaveLength(1 + 133)
  })
})

describe('the skill picker', () => {
  it('lists only the season\'s skills, owned ∩ season in inventory mode', async () => {
    const s1 = await mount(SkillLibrary, { mode: 'select', gameSeason: 'S1' })
    const names = skillNames(s1.root)
    expect(names).not.toContain('疑兵盜城')
    expect(names).not.toContain('龍騎兵')
    expect(names).toContain('紅蓮之炎')
    app!.unmount()
    const owned = await mount(SkillLibrary, { mode: 'select', gameSeason: 'S2', filterOwned: true, ownedSkills: ['疑兵盜城', '合盟之陣', '紅蓮之炎'] })
    // 合盟之陣 is owned but S3.
    expect(skillNames(owned.root).sort()).toEqual(['疑兵盜城', '紅蓮之炎'].sort())
  })

  it('offers only the types its list has', async () => {
    const { root } = await mount(SkillLibrary, { mode: 'select', gameSeason: 'S1' })
    const types = [...root.querySelectorAll('.el-option')].map((el) => el.textContent)
    const shown = new Set(skillNames(root).map((n) => skills.value.find((s) => s.name === n)!.type))
    expect(types.filter((t) => !['S', 'A', 'B'].includes(t!))).toEqual(['指揮', '主動', '突擊', '被動', '兵種', '陣法'].filter((t) => shown.has(t)))
  })
})

describe('a slot', () => {
  it('marks an off-season hero and skill in place, with the season named', async () => {
    const hero = heroes.value.find((h) => h.name === '伊達政宗')!
    const skill1 = skills.value.find((s) => s.name === '疑兵盜城')!
    const skill2 = skills.value.find((s) => s.name === '紅蓮之炎')!
    const { root } = await mount(LineupSlot, {
      title: '大將', role: 'main', hero, skill1, skill2, stats: { ...hero.stats }, breakthrough: 0,
      gameSeason: 'S1', gameSeasonMark: { hero: true, skills: [1] },
    })
    expect(root.querySelector('[data-testid="season-off-hero"]')?.textContent).toBe('非 S1')
    const skillMarks = root.querySelectorAll('[data-testid="season-off-skill"]')
    expect(skillMarks).toHaveLength(1)
    expect(skillMarks[0].parentElement?.textContent).toContain('疑兵盜城')
  })

  it('shows a hero\'s slot as filled whether marked or not (no empty-slot 選擇 beside the portrait)', async () => {
    const hero = heroes.value.find((h) => h.name === '織田信長')!
    for (const gameSeasonMark of [null, { hero: true, skills: [] }]) {
      const { root } = await mount(LineupSlot, { title: '大將', role: 'main', hero, stats: { ...hero.stats }, gameSeason: 'S1', gameSeasonMark })
      expect([...root.querySelectorAll('span')].some((el) => el.textContent === '選擇')).toBe(false)
      app!.unmount()
      app = null
    }
  })

  it('marks nothing when everything fits', async () => {
    const hero = heroes.value.find((h) => h.name === '織田信長')!
    const { root } = await mount(LineupSlot, { title: '大將', role: 'main', hero, stats: { ...hero.stats }, gameSeason: 'S1', gameSeasonMark: null })
    expect(root.querySelector('[data-testid^="season-off"]')).toBeNull()
  })
})
