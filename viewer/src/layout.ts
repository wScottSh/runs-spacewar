import { WORLD, type Arc, type Group, type Net, type State, type Verb } from './canvas/model'

export type Kind = 'game' | 'interface' | 'presentation'

export interface Field {
  name: string
  type: string
  init: string | null
}

export interface RunsRecord {
  name: string
  kind: Kind | null
  file: string | null
  count: number | null
  stream: boolean
  fields: Field[]
}

export interface RunsProcessor {
  name: string
  file: string | null
  params: string[]
  side: 'game' | 'presentation' | null
  mixed: boolean
  reads: string[]
  writes: string[]
}

export interface RunsNet {
  title: string
  records: RunsRecord[]
  processors: RunsProcessor[]
}

export const recordId = (name: string) => `record:${name}`
export const processorId = (name: string) => `processor:${name}`

const CHAR_W = 5.4
const LINE_H = 10
const CELL_W = 210
const CELL_H = 64
const PLACE_GAP = 60
const BLOCK_GAP = 140

/** A collection's count as RUNS writes it: octal, with a leading 0. */
export const countLabel = (count: number | null) => (count ? `[0${count.toString(8)}]` : '')

export const fieldLine = (f: Field) => (f.init === null ? `${f.name}: ${f.type}` : `${f.name} = ${f.init}`)

const radius = (lines: string[]) => {
  const w = Math.max(...lines.map((l) => l.length), 4) * CHAR_W
  const h = lines.length * LINE_H
  return Math.max(24, Math.ceil(Math.hypot(w / 2, h / 2)) + 8)
}

interface Region {
  id: string
  label: string
  side: 'left' | 'center' | 'right'
  records: RunsRecord[]
  processors: RunsProcessor[]
}

/** Which region each Record and Processor is drawn in: by kind when the
 * Records have kinds, otherwise by the file each Processor is written in,
 * with a Record that several files' Processors touch in the middle. */
const regions = (net: RunsNet): Region[] => {
  const kinds = net.records.some((r) => r.kind)
  if (kinds) {
    const byKind = (k: Kind) => net.records.filter((r) => r.kind === k)
    return [
      { id: 'game', label: 'game', side: 'left', records: byKind('game'), processors: net.processors.filter((p) => p.side === 'game' && !p.mixed) },
      { id: 'interface', label: 'interface', side: 'center', records: byKind('interface'), processors: [] },
      { id: 'mixed', label: 'touches game and presentation', side: 'center', records: [], processors: net.processors.filter((p) => p.mixed) },
      { id: 'presentation', label: 'presentation', side: 'right', records: byKind('presentation'), processors: net.processors.filter((p) => p.side === 'presentation' && !p.mixed) },
    ]
  }
  const files = [...new Set(net.processors.map((p) => p.file ?? '?'))]
  const touchedBy = new Map<string, Set<string>>()
  for (const p of net.processors) for (const r of [...p.reads, ...p.writes]) {
    if (!touchedBy.has(r)) touchedBy.set(r, new Set())
    touchedBy.get(r)!.add(p.file ?? '?')
  }
  const home = (r: RunsRecord) => {
    const fs = touchedBy.get(r.name)
    return fs && fs.size === 1 ? [...fs][0] : 'shared'
  }
  const out: Region[] = [{ id: 'shared', label: 'touched from several files', side: 'center', records: net.records.filter((r) => home(r) === 'shared'), processors: [] }]
  for (const f of files)
    out.push({ id: f, label: `${f}.runs`, side: 'left', records: net.records.filter((r) => home(r) === f), processors: net.processors.filter((p) => (p.file ?? '?') === f) })
  return out
}

interface Block {
  region: Region
  w: number
  h: number
  place: (x0: number, y0: number) => { states: State[]; verbs: Verb[] }
}

const placeOf = (r: RunsRecord, group: string, x: number, y: number, rad: number, lines: string[]): State => ({
  id: recordId(r.name),
  label: `${r.stream ? 'stream ' : ''}${r.name}${countLabel(r.count)}`,
  marks: 0,
  seenBy: 'all',
  group,
  x,
  y,
  r: rad,
  lines,
})

/** A region's places in rows no wider than its Processors' grid, then the
 * grid; or, for a region of places alone in the wide layout, one column. */
const block = (region: Region, opts: { vertical: boolean; maxCols: number }): Block => {
  const records = region.records.map((r) => ({ r, lines: r.fields.map(fieldLine) })).map((x) => ({ ...x, rad: radius(x.lines) }))
  const n = region.processors.length
  const cols = opts.vertical ? 1 : Math.max(1, Math.min(opts.maxCols, Math.ceil(Math.sqrt(n * 1.6))))
  const rows = Math.ceil(n / cols)
  const verbsW = n ? cols * CELL_W : 0
  const rowW = Math.max(verbsW, opts.maxCols * CELL_W, ...records.map((x) => 2 * x.rad))
  const placeRows: { items: typeof records; w: number; h: number }[] = []
  for (const x of records) {
    const d = 2 * x.rad
    const last = placeRows[placeRows.length - 1]
    if (!opts.vertical && last && last.w + PLACE_GAP + d <= rowW) {
      last.items.push(x)
      last.w += PLACE_GAP + d
      last.h = Math.max(last.h, d)
    } else placeRows.push({ items: [x], w: d, h: d })
  }
  const placesW = Math.max(0, ...placeRows.map((r) => r.w))
  const placesH = placeRows.reduce((s, r) => s + r.h + PLACE_GAP, 0)
  const w = Math.max(placesW, verbsW, 1)
  const h = placesH + rows * CELL_H
  return {
    region,
    w,
    h,
    place: (x0, y0) => {
      const states: State[] = []
      let cy = y0
      for (const row of placeRows) {
        let cx = x0 + (w - row.w) / 2
        for (const x of row.items) {
          states.push(placeOf(x.r, region.id, cx + x.rad, cy + row.h / 2, x.rad, x.lines))
          cx += 2 * x.rad + PLACE_GAP
        }
        cy += row.h + PLACE_GAP
      }
      const vy = y0 + placesH
      const vx = x0 + (w - verbsW) / 2
      const verbs: Verb[] = region.processors.map((p, i) => ({
        id: processorId(p.name),
        label: p.params.length ? `${p.name}(${p.params.join(', ')})` : p.name,
        by: p.mixed ? 'mixed' : p.side ?? WORLD,
        priority: 0,
        weight: 1,
        group: region.id,
        x: Math.round(vx + (i % cols) * CELL_W + CELL_W / 2),
        y: Math.round(vy + Math.floor(i / cols) * CELL_H + CELL_H / 2),
      }))
      return { states, verbs }
    },
  }
}

/** The RUNS Network as the canvas draws it: Records as places, Processors
 * as transitions, a dotted line for each Record a Processor reads and an
 * arrow for each it writes. */
export function toCanvas(net: RunsNet, narrow = false): Net {
  const rs = regions(net).filter((r) => r.records.length || r.processors.length)
  const states: State[] = []
  const verbs: Verb[] = []
  let y = 0
  if (narrow) {
    // One column, two Processors wide, for a phone held upright.
    for (const r of rs) {
      const b = block(r, { vertical: false, maxCols: 2 })
      const got = b.place(-b.w / 2, y)
      states.push(...got.states)
      verbs.push(...got.verbs)
      y += b.h + BLOCK_GAP
    }
    return finish(net, rs, states, verbs)
  }
  const center = rs.filter((r) => r.side === 'center').map((r) => block(r, { vertical: r.processors.length === 0, maxCols: 99 }))
  const others = rs.filter((r) => r.side !== 'center').map((r) => block(r, { vertical: false, maxCols: 99 }))
  const centerW = Math.max(0, ...center.map((b) => b.w))
  for (const b of center) {
    const got = b.place(-b.w / 2, y)
    states.push(...got.states)
    verbs.push(...got.verbs)
    y += b.h + BLOCK_GAP
  }
  const kinds = net.records.some((r) => r.kind)
  const columns: Record<'left' | 'right', { y: number; blocks: Block[] }> = { left: { y: 0, blocks: [] }, right: { y: 0, blocks: [] } }
  for (const b of others) {
    const side = kinds ? (b.region.side as 'left' | 'right') : columns.left.y <= columns.right.y ? 'left' : 'right'
    const col = columns[side]
    const x0 = side === 'left' ? -centerW / 2 - BLOCK_GAP - b.w : centerW / 2 + BLOCK_GAP
    const got = b.place(x0, col.y)
    states.push(...got.states)
    verbs.push(...got.verbs)
    col.y += b.h + BLOCK_GAP
  }
  return finish(net, rs, states, verbs)
}

const finish = (net: RunsNet, rs: Region[], states: State[], verbs: Verb[]): Net => {
  const arcs: Arc[] = net.processors.flatMap((p) => [
    ...p.reads.map((r): Arc => ({ kind: 'need', state: recordId(r), verb: processorId(p.name), count: 1 })),
    ...p.writes.map((r): Arc => ({ kind: 'give', state: recordId(r), verb: processorId(p.name), count: 1 })),
  ])
  const groups: Group[] = rs.map((r) => ({ id: r.id, label: r.label }))
  return {
    title: net.title,
    seats: [
      { id: 'game', name: 'game', color: '#2e6f9e' },
      { id: 'presentation', name: 'presentation', color: '#b8662a' },
      { id: 'mixed', name: 'game and presentation', color: '#c0392b' },
    ],
    groups,
    states,
    verbs,
    arcs,
  }
}
