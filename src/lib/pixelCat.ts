// Pixel-cat easter egg for the sidebar brand glyph: sprite data plus the
// glyph-to-sprite pixel morph planner. Sprites are 16x16 string rows where
// each char is a palette key and '.' is transparent.

export type CatSpriteId = 'head' | 'body'

export interface PixelPath { fill: string; d: string }
export interface PixelMove {
  from: [number, number]  // glyph cell top-left, 0.5-unit cells
  to: [number, number]    // sprite pixel top-left, 1-unit cells
  color: string
  fade: boolean           // spare glyph cell with no sprite pixel to land on
  delay: number           // ms
}
export interface CatSprite {
  frames: PixelPath[][]
  timeline: number[]      // frame index per 100ms tick, loops
  pixels: { x: number; y: number; color: string }[]  // idle frame, morph targets
}

export const CAT_TICK_MS = 100
const GRID = 16

const PALETTE: Partial<Record<string, string>> = {
  o: '#3f2814', f: '#bc8a58', d: '#7a4622', p: '#e3b394', l: '#f1dcbc',
  w: '#fbf3e6', e: '#bcc23c', k: '#1f1a10', n: '#cc7d5e',
}

const HEAD = [
  '.o............o.',
  '.oo..........oo.',
  '.ofo........ofo.',
  '.ofpo......opfo.',
  '.ofppooooooppfo.',
  'offpffdffdffpffo',
  'offffdfddfdffffo',
  'oflooolfflooolfo',
  'oflekelfflekelfo',
  'offlllfffflllffo',
  'odfffflfflffffdo',
  '.offfwwnnwwfffo.',
  '.offwwwoowwwffo.',
  '..ofwwowwowwfo..',
  '...oowwwwwwoo...',
  '.....oooooo.....',
]

const BODY = [
  '.o........o.....',
  '.oo......oo.....',
  '.ofo....ofo.....',
  '.ofpoooopfo.....',
  '.ofdfddfdfo.....',
  '.oooolloooo.....',
  '.oekellekeo.....',
  '.olfwnnwflo.....',
  '..ofwoowfo......',
  '.offfwwfffo.....',
  '.offwwwwffo.....',
  'offfwwwwfffo....',
  'offdfwwfdffo....',
  'offdffffdffo....',
  'owwwoffowwwo....',
  '.oooooooooo.....',
]

const TAILS: Partial<Record<number, string>>[] = [
  { 7: '.............oo.', 8: '............odo.', 9: '............ofo.', 10: '............ofo.', 11: '...........ofo..', 12: '...........ffo..', 13: '............o...' },
  { 8: '..............oo', 9: '.............odo', 10: '............ofo.', 11: '...........ofo..', 12: '...........ffo..', 13: '............o...' },
  { 12: '............ooo.', 13: '...........fffdo', 14: '...........oooo.' },
]

// Replace whole rows.
const withRows = (base: string[], rows: Partial<Record<number, string>>) => base.map((r, y) => rows[y] ?? r)

// Paint non-transparent chars of a layer over the base.
const overlay = (base: string[], layer: Partial<Record<number, string>>) => base.map((row, y) => {
  const src = layer[y]
  if (!src) return row
  return [...row].map((c, x) => (src.charAt(x) === '.' ? c : src.charAt(x))).join('')
})

const colorOf = (c: string) => PALETTE[c] ?? '#000'

function framePaths(rows: string[]): PixelPath[] {
  const runs = new Map<string, string[]>()
  rows.forEach((row, y) => {
    for (let x = 0; x < GRID;) {
      const c = row.charAt(x)
      let n = 1
      while (x + n < GRID && row.charAt(x + n) === c) n++
      if (c !== '.') runs.set(c, [...(runs.get(c) ?? []), `M${x} ${y}h${n}v1h-${n}z`])
      x += n
    }
  })
  return [...runs].map(([c, d]) => ({ fill: colorOf(c), d: d.join('') }))
}

// Expand [frameKey, ticks] pairs into a per-tick timeline of frame indices.
// The first frame is the idle pose the morph lands on.
function buildSprite(frames: [string, string[]][], script: [string, number][]): CatSprite {
  const keys = frames.map(([k]) => k)
  const idle = frames[0]?.[1] ?? []
  return {
    frames: frames.map(([, rows]) => framePaths(rows)),
    timeline: script.flatMap(([k, n]): number[] => Array(n).fill(keys.indexOf(k))),
    pixels: idle.flatMap((row, y) => [...row].flatMap((c, x) => (c === '.' ? [] : [{ x, y, color: colorOf(c) }]))),
  }
}

function headSprite(): CatSprite {
  return buildSprite([
    ['idle', HEAD],
    ['half', withRows(HEAD, { 7: 'oflooolfflooolfo', 8: 'oflokolfflokolfo' })],
    ['shut', withRows(HEAD, { 7: 'oflffflfflffflfo', 8: 'oflooolfflooolfo' })],
    ['ear', withRows(HEAD, { 0: '.o..............', 1: '.oo...........oo', 2: '.ofo.........ofo' })],
  ], [
    ['idle', 20], ['half', 2], ['shut', 3], ['half', 2],
    ['idle', 16], ['ear', 2], ['idle', 1], ['ear', 2], ['idle', 12],
  ])
}

function bodySprite(): CatSprite {
  const frames = TAILS.flatMap((tail, i): [string, string[]][] => {
    const open = overlay(BODY, tail)
    return [[`t${i}`, open], [`t${i}b`, withRows(open, { 5: '.offfllfffo.....', 6: '.ooooffoooo.....' })]]
  })
  // Tail sways 0-1-2-1; eyes blink a few times per loop.
  const sway = [0, 0, 0, 1, 1, 1, 2, 2, 2, 1, 1, 1]
  const blinkAt = new Set(['1:4', '3:2', '3:5'])
  const script: [string, number][] = []
  for (let loop = 0; loop < 4; loop++) {
    sway.forEach((s, i) => script.push([`t${s}${blinkAt.has(`${loop}:${i}`) ? 'b' : ''}`, 1]))
  }
  return buildSprite(frames, script)
}

export const CAT_SPRITES: Record<CatSpriteId, CatSprite> = { head: headSprite(), body: bodySprite() }

/** Rasterize a circled glyph (CSS ring + centered text) onto a 32-cell grid
 *  in 16-unit space. Returns top-left corners of covered cells. */
export function rasterizeGlyph(glyph: string, font: string, ringWidthPx: number, sizePx: number): [number, number][] {
  const SCALE = 4, S = sizePx * SCALE, cells = 32, cell = S / cells
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = S
  const g = canvas.getContext('2d', { willReadFrequently: true })
  if (!g) return []
  g.lineWidth = ringWidthPx * SCALE
  g.beginPath()
  g.arc(S / 2, S / 2, (S - g.lineWidth) / 2, 0, Math.PI * 2)
  g.stroke()
  g.font = font.replace(/(\d+(\.\d+)?)px/, (_, n) => `${parseFloat(n) * SCALE}px`)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillText(glyph, S / 2, S / 2)
  const data = g.getImageData(0, 0, S, S).data
  const out: [number, number][] = []
  for (let cy = 0; cy < cells; cy++) for (let cx = 0; cx < cells; cx++) {
    let sum = 0
    for (let y = 0; y < cell; y++) for (let x = 0; x < cell; x++) sum += data[((cy * cell + y) * S + cx * cell + x) * 4 + 3] ?? 0
    if (sum / (cell * cell * 255) > 0.3) out.push([cx / 2, cy / 2])
  }
  return out
}

/** Pair every sprite pixel with the nearest free glyph cell; spare glyph
 *  cells fly to their nearest sprite pixel and fade. Delays ripple outward. */
export function planMorph(sources: [number, number][], sprite: CatSprite, rippleMs = 320): PixelMove[] {
  interface Pt { cx: number; cy: number }
  const srcs = sources.map(([x, y]) => ({ x, y, cx: x + 0.25, cy: y + 0.25 }))
  const tgts = sprite.pixels.map(p => ({ ...p, cx: p.x + 0.5, cy: p.y + 0.5 }))
  const nearest = <T extends Pt>(from: Pt, pool: T[], used?: Set<T>) => {
    let best: T | undefined, bd = Infinity
    for (const p of pool) {
      if (used?.has(p)) continue
      const d = (p.cx - from.cx) ** 2 + (p.cy - from.cy) ** 2
      if (d < bd) { bd = d; best = p }
    }
    return best
  }

  const used = new Set<(typeof srcs)[number]>()
  const moves: PixelMove[] = []
  // Deterministic shuffle so greedy matching doesn't sweep in raster order.
  const order = tgts.map((t, i) => ({ t, k: (i * 7919) % 97 })).sort((a, b) => a.k - b.k).map(o => o.t)
  for (const t of order) {
    const s = nearest(t, srcs, used) ?? nearest(t, srcs)
    if (!s) break
    used.add(s)
    moves.push({ from: [s.x, s.y], to: [t.x, t.y], color: t.color, fade: false, delay: 0 })
  }
  for (const s of srcs) {
    const t = used.has(s) ? undefined : nearest(s, tgts)
    if (t) moves.push({ from: [s.x, s.y], to: [t.x, t.y], color: t.color, fade: true, delay: 0 })
  }
  for (const m of moves) {
    const r = Math.hypot(m.from[0] + 0.25 - 8, m.from[1] + 0.25 - 8) / 8
    m.delay = r * rippleMs + ((m.from[0] * 14 + m.from[1] * 26) % 60)
  }
  return moves
}
