// Reordering teams in a team list. A mouse drags a row (a marker shows the gap it would land in); touch and keyboard use the
// move buttons (TeamMoveButtons.vue), and Alt + up or down moves the focused row. Only this list's own drag counts here, and it
// carries no data LineupSlot reads, so hero and skill drags and these cannot act on each other.
import { nextTick, ref } from 'vue'

const TEAM_DRAG_TYPE = 'application/x-nobunaga-team'

// The gap (0..n, n after the last row) a pointer at clientY points at, from the rows' centres.
const gapAt = (centres: number[], y: number): number => {
  const next = centres.findIndex((centre) => y < centre)
  return next < 0 ? centres.length : next
}

// The index a row lands on when dropped in `gap`; null when that leaves it where it is.
const dropTarget = (from: number, gap: number): number | null => {
  const to = gap > from ? gap - 1 : gap
  return to === from ? null : to
}

const centreOf = (row: Element): number => {
  const box = row.getBoundingClientRect()
  return box.top + box.height / 2
}

export function useTeamReorder(count: () => number, move: (from: number, to: number) => void) {
  const dragFrom = ref<number | null>(null)
  const dropGap = ref<number | null>(null)

  const onDragStart = (e: DragEvent, idx: number) => {
    if (!e.dataTransfer) return
    e.dataTransfer.setData(TEAM_DRAG_TYPE, String(idx))
    e.dataTransfer.effectAllowed = 'move'
    dragFrom.value = idx
  }
  const onDragOver = (e: DragEvent) => {
    if (dragFrom.value === null) return
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
    const rows = (e.currentTarget as HTMLElement).querySelectorAll('[data-team-row]')
    const gap = gapAt([...rows].map(centreOf), e.clientY)
    dropGap.value = dropTarget(dragFrom.value, gap) === null ? null : gap
  }
  const onDragLeave = (e: DragEvent) => {
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) dropGap.value = null
  }
  const onDragEnd = () => {
    dragFrom.value = null
    dropGap.value = null
  }
  const onDrop = (e: DragEvent) => {
    if (dragFrom.value === null) return
    e.preventDefault()
    const to = dropGap.value === null ? null : dropTarget(dragFrom.value, dropGap.value)
    if (to !== null) move(dragFrom.value, to)
    onDragEnd()
  }
  const dropClass = (idx: number) => ({
    'opacity-50': dragFrom.value === idx,
    'team-drop-before': dropGap.value === idx,
    'team-drop-after': dropGap.value === idx + 1 && idx === count() - 1,
  })

  // After a move a row's node holds another team, so the focus goes to where this one landed.
  const refocus = (list: Element | null, to: number, control?: string) => {
    const row = list?.querySelectorAll<HTMLElement>('[data-team-row]')[to]
    const same = control ? row?.querySelector<HTMLElement>(`[data-move="${control}"]:not(:disabled)`) : null
    ;(same ?? row)?.focus()
  }
  const shift = async (e: Event, idx: number, step: -1 | 1) => {
    const to = idx + step
    if (to < 0 || to >= count()) return
    const source = e.currentTarget as HTMLElement
    const list = source.closest('[data-team-list]')
    const control = source.dataset.move
    move(idx, to)
    await nextTick()
    refocus(list, to, control)
  }
  const onRowKey = (e: KeyboardEvent, idx: number) => {
    const step = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' ? 1 : 0
    if (!e.altKey || step === 0) return
    e.preventDefault()
    void shift(e, idx, step)
  }

  return { onDragStart, onDragOver, onDragLeave, onDragEnd, onDrop, dropClass, shift, onRowKey }
}
