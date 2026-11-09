import type { Arc, Net } from './model'
import { PRIORITY_R, STATE_R, borderPoint, groupHulls, priorityBadge, type Pt, type Shape } from './geometry'

/** Routes run on a grid of this pitch; hand-placed bend points snap to it. */
export const PITCH = 5

const CLEAR = 4
const MARGIN = 80
const STEP = PITCH
const BEND = 24
const CROSS = 55
const BESIDE = 3
const SPARE_PORT = 160
const OVERLAP = 4000
const THROUGH_NODE = 600
/** Weighted A*: trades a little optimality for far fewer expansions. */
const GREED = 1.3

export type ArcKey = string
export const arcKey = (a: Pick<Arc, 'kind' | 'state' | 'verb'>): ArcKey => `${a.kind}|${a.state}|${a.verb}`
/** Arcs that leave or reach one state with one kind form a cable: one trunk that branches. */
export const cableKey = (a: Pick<Arc, 'kind' | 'state'>) => `${a.state}|${a.kind}`

const DX = [1, 0, -1, 0]
const DY = [0, 1, 0, -1]
const E = 0
const S = 1
const W = 2
const N = 3
const axis = (d: number) => d & 1
const back = (d: number) => (d + 2) & 3

interface Port {
  cell: number
  /** direction pointing away from the node, along the stub */
  out: number
  border: Pt
  cost: number
}

interface Grid {
  x0: number
  y0: number
  cols: number
  rows: number
  /** node index that blocks the cell, -1 free, -2 more than one node */
  owner: Int32Array
  /** cable index occupying the cell along each axis, -1 free */
  occ: [Int32Array, Int32Array]
}

const FREE = -1
const MANY = -2

const makeGrid = (box: { x0: number; y0: number; x1: number; y1: number }): Grid => {
  const x0 = Math.floor((box.x0 - MARGIN) / PITCH) * PITCH
  const y0 = Math.floor((box.y0 - MARGIN) / PITCH) * PITCH
  const cols = Math.ceil((box.x1 + MARGIN - x0) / PITCH) + 1
  const rows = Math.ceil((box.y1 + MARGIN - y0) / PITCH) + 1
  const n = cols * rows
  return { x0, y0, cols, rows, owner: new Int32Array(n).fill(FREE), occ: [new Int32Array(n).fill(FREE), new Int32Array(n).fill(FREE)] }
}

const cellAt = (g: Grid, x: number, y: number) => {
  const cx = Math.min(g.cols - 1, Math.max(0, Math.round((x - g.x0) / PITCH)))
  const cy = Math.min(g.rows - 1, Math.max(0, Math.round((y - g.y0) / PITCH)))
  return cy * g.cols + cx
}
const ptOf = (g: Grid, c: number): Pt => ({ x: g.x0 + (c % g.cols) * PITCH, y: g.y0 + Math.floor(c / g.cols) * PITCH })

const claim = (g: Grid, node: number, inside: (x: number, y: number) => boolean, x0: number, y0: number, x1: number, y1: number) => {
  const cx0 = Math.max(0, Math.ceil((x0 - g.x0) / PITCH))
  const cx1 = Math.min(g.cols - 1, Math.floor((x1 - g.x0) / PITCH))
  const cy0 = Math.max(0, Math.ceil((y0 - g.y0) / PITCH))
  const cy1 = Math.min(g.rows - 1, Math.floor((y1 - g.y0) / PITCH))
  for (let cy = cy0; cy <= cy1; cy++)
    for (let cx = cx0; cx <= cx1; cx++) {
      if (!inside(g.x0 + cx * PITCH, g.y0 + cy * PITCH)) continue
      const c = cy * g.cols + cx
      g.owner[c] = g.owner[c] === FREE || g.owner[c] === node ? node : MANY
    }
}

const claimRect = (g: Grid, node: number, cx: number, cy: number, hw: number, hh: number) =>
  claim(g, node, (x, y) => Math.abs(x - cx) <= hw && Math.abs(y - cy) <= hh, cx - hw, cy - hh, cx + hw, cy + hh)
const claimCircle = (g: Grid, node: number, cx: number, cy: number, r: number) =>
  claim(g, node, (x, y) => Math.hypot(x - cx, y - cy) <= r, cx - r, cy - r, cx + r, cy + r)

interface Node {
  id: string
  index: number
  shape: Shape
  /** the drawn extent around a state: an outcome ring is wider than the circle */
  r: number
  badge: boolean
}

const blockNodes = (g: Grid, net: Net, nodes: Map<string, Node>, shapes: Map<string, Shape>) => {
  groupHulls(net, shapes).forEach(({ group, box }, i) =>
    claimRect(g, nodes.size + i, box.x0 + 14 + (group.label.length * 7) / 2, box.y0 + 14, (group.label.length * 7) / 2 + 4, 9),
  )
  for (const n of nodes.values()) {
    const s = n.shape
    if (s.kind === 'circle') claimCircle(g, n.index, s.x, s.y, n.r + CLEAR)
    else {
      claimRect(g, n.index, s.x, s.y, s.w / 2 + CLEAR, s.h / 2 + CLEAR)
      if (n.badge) {
        const b = priorityBadge(s.w)
        // the extra pitch keeps an input's end marker on a nearby top port from touching the badge
        claimCircle(g, n.index, s.x + b.x, s.y + b.y, PRIORITY_R + CLEAR + PITCH)
      }
    }
  }
  for (const p of net.states) {
    const n = nodes.get(p.id)
    if (!n) continue
    const lw = (p.label.length * 5.8) / 2 + 3
    claimRect(g, n.index, p.x, p.y + (p.r ?? STATE_R) + 6 + 7, lw, 9)
    if (p.seenBy !== 'all') {
      const text = p.seenBy.length ? p.seenBy.join(', ') : 'nobody'
      const w = 22 + text.length * 5.6
      claimRect(g, n.index, p.x + STATE_R - 6 + w / 2, p.y - STATE_R - 6, w / 2 + 3, 11)
    }
  }
}

/** The stub from a port to its node crosses only that node's clearance, never another node. */
const stubClear = (g: Grid, from: number, out: number, node: number, steps: number) => {
  let c = from
  const step = DY[back(out)] * g.cols + DX[back(out)]
  for (let i = 0; i < steps; i++) {
    c += step
    if (g.owner[c] !== FREE && g.owner[c] !== node) return false
  }
  return true
}

const statePorts = (g: Grid, n: Node): Port[] => {
  const s = n.shape as Extract<Shape, { kind: 'circle' }>
  const ports: Port[] = []
  const reach = n.r + CLEAR + 0.5
  for (const out of [E, W, N]) {
    const horizontal = axis(out) === 0
    const along = horizontal ? s.y : s.x
    const at = horizontal ? s.x + DX[out] * reach : s.y + DY[out] * reach
    const atC = horizontal ? (out === E ? Math.ceil((at - g.x0) / PITCH) : Math.floor((at - g.x0) / PITCH)) : Math.floor((at - g.y0) / PITCH)
    const lim = s.r - 5
    const lo = Math.ceil((along - lim - (horizontal ? g.y0 : g.x0)) / PITCH)
    const hi = Math.floor((along + lim - (horizontal ? g.y0 : g.x0)) / PITCH)
    for (let k = lo; k <= hi; k++) {
      const cx = horizontal ? atC : k
      const cy = horizontal ? k : atC
      if (cx < 0 || cy < 0 || cx >= g.cols || cy >= g.rows) continue
      const cell = cy * g.cols + cx
      if (g.owner[cell] !== FREE) continue
      const p = ptOf(g, cell)
      const off = horizontal ? p.y - s.y : p.x - s.x
      const depth = Math.sqrt(Math.max(0, s.r * s.r - off * off)) + 2
      const border = horizontal ? { x: s.x + DX[out] * depth, y: p.y } : { x: p.x, y: s.y + DY[out] * depth }
      const steps = Math.round(Math.abs(horizontal ? p.x - s.x : p.y - s.y) / PITCH) - 1
      if (!stubClear(g, cell, out, n.index, steps)) continue
      ports.push({ cell, out, border, cost: Math.abs(off) * 0.6 + (out === N ? 4 : 0) })
    }
  }
  return ports
}

/** Inputs reach a verb from its top or left; outputs leave from its bottom or right. */
const verbPorts = (g: Grid, n: Node, output: boolean): Port[] => {
  const s = n.shape as Extract<Shape, { kind: 'rect' }>
  const ports: Port[] = []
  for (const out of output ? [E, S] : [W, N]) {
    const horizontal = axis(out) === 0
    const half = horizontal ? s.w / 2 : s.h / 2
    const reach = half + CLEAR + 0.5
    const at = horizontal ? s.x + DX[out] * reach : s.y + DY[out] * reach
    const base = horizontal ? g.x0 : g.y0
    const atC = DX[out] + DY[out] > 0 ? Math.ceil((at - base) / PITCH) : Math.floor((at - base) / PITCH)
    const along = horizontal ? s.y : s.x
    const lim = horizontal ? s.h / 2 - 1 : s.w / 2 - 6
    const lo = Math.ceil((along - lim - (horizontal ? g.y0 : g.x0)) / PITCH)
    const hi = Math.floor((along + lim - (horizontal ? g.y0 : g.x0)) / PITCH)
    for (let k = lo; k <= hi; k++) {
      const cx = horizontal ? atC : k
      const cy = horizontal ? k : atC
      if (cx < 0 || cy < 0 || cx >= g.cols || cy >= g.rows) continue
      const cell = cy * g.cols + cx
      if (g.owner[cell] !== FREE) continue
      const p = ptOf(g, cell)
      const off = horizontal ? p.y - s.y : p.x - s.x
      const border = horizontal ? { x: s.x + DX[out] * (s.w / 2 + 2), y: p.y } : { x: p.x, y: s.y + DY[out] * (s.h / 2 + 2) }
      const steps = Math.round(Math.abs(horizontal ? p.x - s.x : p.y - s.y) / PITCH) - 1
      if (!stubClear(g, cell, out, n.index, steps)) continue
      ports.push({ cell, out, border, cost: Math.abs(off) * (horizontal ? 0.6 : 0.15) })
    }
  }
  return ports
}

/** Binary min-heap of search states keyed by f. */
class Heap {
  keys = new Float64Array(1024)
  vals = new Int32Array(1024)
  size = 0
  push(k: number, v: number) {
    if (this.size === this.keys.length) {
      const k2 = new Float64Array(this.size * 2)
      const v2 = new Int32Array(this.size * 2)
      k2.set(this.keys)
      v2.set(this.vals)
      this.keys = k2
      this.vals = v2
    }
    let i = this.size++
    while (i > 0) {
      const p = (i - 1) >> 1
      if (this.keys[p] <= k) break
      this.keys[i] = this.keys[p]
      this.vals[i] = this.vals[p]
      i = p
    }
    this.keys[i] = k
    this.vals[i] = v
  }
  pop(): number {
    const top = this.vals[0]
    const k = this.keys[--this.size]
    const v = this.vals[this.size]
    let i = 0
    for (;;) {
      let c = 2 * i + 1
      if (c >= this.size) break
      if (c + 1 < this.size && this.keys[c + 1] < this.keys[c]) c++
      if (this.keys[c] >= k) break
      this.keys[i] = this.keys[c]
      this.vals[i] = this.vals[c]
      i = c
    }
    this.keys[i] = k
    this.vals[i] = v
    return top
  }
  topKey() {
    return this.keys[0]
  }
}

interface Start {
  cell: number
  dir: number
  cost: number
}

interface Target {
  /** cost of finishing at this cell having arrived moving in `dir`, or undefined if the cell is not a goal */
  finish: (cell: number, dir: number) => number | undefined
  box: { cx0: number; cy0: number; cx1: number; cy1: number }
}

interface Found {
  cells: number[]
  dirs: number[]
}

/** Search buffers outlive one routing call: a drag routes every frame, and allocating them each time shows. */
let scratch: { g: Float64Array; seen: Uint32Array; from: Int32Array; closed: Uint32Array; stamp: number } | undefined

class Searcher {
  g: Float64Array
  seen: Uint32Array
  from: Int32Array
  closed: Uint32Array
  cross = CROSS
  greed = GREED
  /** expansions allowed per search; a drag gives up on hard arcs rather than drop frames */
  budget = Infinity
  heap = new Heap()
  constructor(readonly grid: Grid) {
    const n = grid.cols * grid.rows * 4
    if (!scratch || scratch.g.length < n || scratch.stamp > 4e9)
      scratch = { g: new Float64Array(n), seen: new Uint32Array(n), from: new Int32Array(n), closed: new Uint32Array(n), stamp: 0 }
    this.g = scratch.g
    this.seen = scratch.seen
    this.from = scratch.from
    this.closed = scratch.closed
  }

  /**
   * Cheapest path from any start to the target. `mine` marks cells of the cable being routed, which a branch
   * may leave but not re-enter. `lenient` turns walls into costs so a path always exists.
   */
  run(cable: number, starts: Start[], target: Target, mine: Uint8Array | null, lenient: boolean): Found | undefined {
    const { grid, g, seen, from, heap, greed } = this
    const { cols, rows, owner, occ } = grid
    const stamp = ++scratch!.stamp
    heap.size = 0
    const { cx0, cy0, cx1, cy1 } = target.box
    const h = (c: number) => {
      const x = c % cols
      const y = (c - x) / cols
      const ox = Math.max(0, cx0 - x, x - cx1)
      const oy = Math.max(0, cy0 - y, y - cy1)
      return ((ox + oy) * STEP + (ox && oy ? BEND : 0)) * greed
    }
    let best = Infinity
    let bestState = -1
    let budget = this.budget
    for (const s of starts) {
      const st = s.cell * 4 + s.dir
      if (seen[st] === stamp && g[st] <= s.cost) continue
      seen[st] = stamp
      g[st] = s.cost
      from[st] = -1
      heap.push(s.cost + h(s.cell), st)
      const fin = target.finish(s.cell, s.dir)
      if (fin !== undefined && s.cost + fin < best) {
        best = s.cost + fin
        bestState = st
      }
    }
    const foreign = (v: number) => v !== FREE && v !== cable
    while (heap.size) {
      if (heap.topKey() >= best) break
      const st = heap.pop()
      if (this.closed[st] === stamp) continue
      this.closed[st] = stamp
      if (--budget < 0) return undefined
      const c = st >> 2
      const d = st & 3
      const gc = g[st]
      const x = c % cols
      const y = (c - x) / cols
      for (let nd = 0; nd < 4; nd++) {
        if (nd === back(d)) continue
        const nx = x + DX[nd]
        const ny = y + DY[nd]
        if (nx < 0 || ny < 0 || nx >= cols || ny >= rows) continue
        const n = ny * cols + nx
        if (mine && mine[n]) continue
        const a = axis(nd)
        let cost = gc + STEP
        if (nd !== d) {
          cost += BEND
          if (foreign(occ[a ^ 1][c])) {
            if (!lenient) continue
            cost += OVERLAP
          }
        }
        if (owner[n] !== FREE) {
          if (!lenient) continue
          cost += THROUGH_NODE
        }
        if (foreign(occ[a][c]) || foreign(occ[a][n])) {
          if (!lenient) continue
          cost += OVERLAP
        }
        if (foreign(occ[a ^ 1][n])) cost += this.cross
        const side = a === 0 ? cols : 1
        if ((n - side >= 0 && foreign(occ[a][n - side])) || (n + side < occ[a].length && foreign(occ[a][n + side]))) cost += BESIDE
        const ns = n * 4 + nd
        if (seen[ns] === stamp && g[ns] <= cost) continue
        seen[ns] = stamp
        g[ns] = cost
        from[ns] = st
        const fin = target.finish(n, nd)
        if (fin !== undefined && cost + fin < best) {
          best = cost + fin
          bestState = ns
        }
        heap.push(cost + h(n), ns)
      }
    }
    if (bestState < 0) return undefined
    const cells: number[] = []
    const dirs: number[] = []
    for (let s = bestState; s >= 0; s = from[s]) {
      cells.push(s >> 2)
      dirs.push(s & 3)
    }
    cells.reverse()
    dirs.reverse()
    return { cells, dirs }
  }
}

const portTarget = (g: Grid, ports: Port[], cable: number, lenient: boolean): Target => {
  const byCell = new Map<number, Port[]>()
  for (const p of ports) byCell.set(p.cell, [...(byCell.get(p.cell) ?? []), p])
  let cx0 = Infinity
  let cy0 = Infinity
  let cx1 = -Infinity
  let cy1 = -Infinity
  for (const p of ports) {
    const x = p.cell % g.cols
    const y = (p.cell - x) / g.cols
    cx0 = Math.min(cx0, x)
    cx1 = Math.max(cx1, x)
    cy0 = Math.min(cy0, y)
    cy1 = Math.max(cy1, y)
  }
  return {
    box: { cx0, cy0, cx1, cy1 },
    finish: (cell, dir) => {
      const here = byCell.get(cell)
      if (!here) return undefined
      let best: number | undefined
      for (const p of here) {
        const into = back(p.out)
        const stub = g.occ[axis(into)][cell]
        if (stub !== FREE && stub !== cable && !lenient) continue
        const c = p.cost + (dir === into ? 0 : BEND) + (stub !== FREE && stub !== cable ? OVERLAP : 0)
        if (best === undefined || c < best) best = c
      }
      return best
    },
  }
}

const cellTarget = (g: Grid, cell: number): Target => {
  const x = cell % g.cols
  const y = (cell - x) / g.cols
  return { box: { cx0: x, cy0: y, cx1: x, cy1: y }, finish: (c) => (c === cell ? 0 : undefined) }
}


const simplify = (pts: Pt[]): Pt[] => {
  const out: Pt[] = []
  for (const p of pts) {
    if (out.length && Math.abs(out[out.length - 1].x - p.x) < 1e-6 && Math.abs(out[out.length - 1].y - p.y) < 1e-6) continue
    if (out.length >= 2) {
      const a = out[out.length - 2]
      const b = out[out.length - 1]
      if (Math.abs((b.x - a.x) * (p.y - b.y) - (b.y - a.y) * (p.x - b.x)) < 1e-6 && (b.x - a.x) * (p.x - b.x) + (b.y - a.y) * (p.y - b.y) >= 0) {
        out[out.length - 1] = p
        continue
      }
    }
    out.push(p)
  }
  return out
}

const straight = (from: Shape, to: Shape): Pt[] => {
  const edge = (s: Shape, t: Pt): Pt => {
    const dx = t.x - s.x
    const dy = t.y - s.y
    const len = Math.hypot(dx, dy) || 1
    if (s.kind === 'circle') return { x: s.x + (dx / len) * (s.r + 2), y: s.y + (dy / len) * (s.r + 2) }
    const k = Math.min((s.w / 2 + 2) / Math.abs(dx || 1e-9), (s.h / 2 + 2) / Math.abs(dy || 1e-9))
    return { x: s.x + dx * k, y: s.y + dy * k }
  }
  return [edge(from, to), edge(to, from)]
}

interface Tree {
  /** per cell: the previous cell toward the state, -1 at a root port */
  parent: Map<number, number>
  /** where each root cell's stub meets the state */
  rootPort: Map<number, Pt>
  /** cells where a branch ends at a verb: never a place to attach */
  leaves: Set<number>
}

/** Routes from an earlier full routing, and the nodes that have moved or changed since. */
export interface Prior {
  routes: Map<ArcKey, Pt[]>
  moved: Set<string>
}

class Router {
  readonly nodes = new Map<string, Node>()
  readonly routes = new Map<ArcKey, Pt[]>()
  readonly cables = new Map<string, Arc[]>()
  readonly order: string[] = []
  readonly grid: Grid
  private readonly ids = new Map<string, number>()
  private readonly search: Searcher
  private readonly ports = new Map<string, Port[]>()
  private trees = new Map<string, Tree>()
  /** per cable: the occupancy it wrote, as (axis * cells + cell, previous value) pairs */
  private logs = new Map<string, number[]>()
  private log: number[] = []
  /** cells of the tree being routed now, which its new branches may leave but not re-enter */
  private mine: Uint8Array
  private active: Tree | undefined

  constructor(
    net: Net,
    shapes: Map<string, Shape>,
  ) {
    let i = 0
    for (const p of net.states) {
      const s = shapes.get(p.id)
      if (s?.kind === 'circle') this.nodes.set(p.id, { id: p.id, index: i++, shape: s, r: s.r + (p.ends !== undefined ? 4 : 0), badge: false })
    }
    for (const v of net.verbs) {
      const s = shapes.get(v.id)
      if (s?.kind === 'rect') this.nodes.set(v.id, { id: v.id, index: i++, shape: s, r: 0, badge: v.priority !== 0 })
    }
    const box = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity }
    const grow = (x: number, y: number) => {
      box.x0 = Math.min(box.x0, x)
      box.y0 = Math.min(box.y0, y)
      box.x1 = Math.max(box.x1, x)
      box.y1 = Math.max(box.y1, y)
    }
    for (const n of this.nodes.values()) {
      const s = n.shape
      const hw = s.kind === 'circle' ? s.r + 60 : s.w / 2
      const hh = s.kind === 'circle' ? s.r + 20 : s.h / 2
      grow(s.x - hw, s.y - hh)
      grow(s.x + hw, s.y + hh)
    }
    for (const a of net.arcs) {
      if (!this.nodes.has(a.state) || !this.nodes.has(a.verb)) continue
      for (const p of a.via ?? []) grow(p.x, p.y)
      this.cables.set(cableKey(a), [...(this.cables.get(cableKey(a)) ?? []), a])
    }
    this.grid = makeGrid(Number.isFinite(box.x0) ? box : { x0: 0, y0: 0, x1: 0, y1: 0 })
    blockNodes(this.grid, net, this.nodes, shapes)
    this.search = new Searcher(this.grid)
    this.mine = new Uint8Array(this.grid.cols * this.grid.rows)
    for (const k of this.cables.keys()) this.ids.set(k, this.ids.size)
    const span = (list: Arc[]) => {
      const s = this.nodes.get(list[0].state)!.shape
      return list.reduce((m, a) => {
        const v = this.nodes.get(a.verb)!.shape
        return m + Math.abs(v.x - s.x) + Math.abs(v.y - s.y)
      }, 0)
    }
    this.order = [...this.cables.keys()].sort((a, b) => span(this.cables.get(a)!) - span(this.cables.get(b)!) || (a < b ? -1 : 1))
  }

  private portsOf(id: string, output: boolean) {
    const k = `${id}|${output}`
    let p = this.ports.get(k)
    if (!p) {
      const n = this.nodes.get(id)!
      p = n.shape.kind === 'circle' ? statePorts(this.grid, n) : verbPorts(this.grid, n, output)
      this.ports.set(k, p)
    }
    return p
  }

  private mark(a: number, cell: number, cable: number) {
    const occ = this.grid.occ[a]
    if (occ[cell] === cable) return
    this.log.push(a * occ.length + cell, occ[cell])
    occ[cell] = cable
  }

  private occupy(cable: number, cells: number[], dirs: number[], first: number | undefined, last: number | undefined) {
    for (let i = 0; i < cells.length; i++) {
      if (i > 0) this.mark(axis(dirs[i]), cells[i], cable)
      if (i + 1 < cells.length) this.mark(axis(dirs[i + 1]), cells[i], cable)
    }
    if (first !== undefined) this.mark(axis(first), cells[0], cable)
    if (last !== undefined) this.mark(axis(last), cells[cells.length - 1], cable)
  }

  tune(cross: number, greed: number, budget = Infinity) {
    this.search.cross = cross
    this.search.greed = greed
    this.search.budget = budget
  }

  release(key: string) {
    const cable = this.ids.get(key)!
    const log = this.logs.get(key) ?? []
    const n = this.grid.occ[0].length
    for (let i = log.length - 2; i >= 0; i -= 2) {
      const a = log[i] >= n ? 1 : 0
      const c = log[i] - a * n
      if (this.grid.occ[a][c] === cable) this.grid.occ[a][c] = log[i + 1]
    }
    this.logs.delete(key)
    this.trees.delete(key)
    for (const a of this.cables.get(key)!) this.routes.delete(arcKey(a))
  }

  /**
   * Lays down a cable's arcs exactly where they were, except `skip`, and rebuilds its tree so skipped arcs can
   * branch off it again. False, with nothing laid, when a node now sits on one of them.
   */
  replay(key: string, prior: Map<ArcKey, Pt[]>, skip: Set<ArcKey>) {
    const list = this.cables.get(key)!.filter((a) => !skip.has(arcKey(a)) && !this.runOver(a, prior.get(arcKey(a))))
    for (const a of this.cables.get(key)!) if (!list.includes(a)) skip.add(arcKey(a))
    const own = new Set<number>()
    for (const a of list) own.add(this.nodes.get(a.state)!.index).add(this.nodes.get(a.verb)!.index)
    const paths = list.map((a) => prior.get(arcKey(a)))
    if (paths.some((p) => !p)) return false
    const g = this.grid
    const marks: [number, number][] = []
    const chains: { cells: number[]; border: Pt } [] = []
    for (const pts of paths as Pt[][]) {
      const cells: number[] = []
      let orthogonal = true
      for (let j = 1; j < pts.length; j++) {
        const p = pts[j - 1]
        const q = pts[j]
        const a = Math.abs(p.y - q.y) < 1e-6 ? 0 : Math.abs(p.x - q.x) < 1e-6 ? 1 : -1
        if (a < 0) {
          orthogonal = false
          continue
        }
        const c0 = cellAt(g, p.x, p.y)
        const c1 = cellAt(g, q.x, q.y)
        const step = a === 0 ? Math.sign(c1 - c0) : Math.sign(c1 - c0) * g.cols
        for (let c = c0; ; c += step) {
          if (g.owner[c] !== FREE && !own.has(g.owner[c])) return false
          marks.push([a, c])
          if (cells[cells.length - 1] !== c) cells.push(c)
          if (c === c1 || !step) break
        }
      }
      if (!orthogonal) continue
      let lo = 0
      let hi = cells.length - 1
      while (lo <= hi && g.owner[cells[lo]] !== FREE) lo++
      while (hi >= lo && g.owner[cells[hi]] !== FREE) hi--
      if (lo <= hi) chains.push({ cells: cells.slice(lo, hi + 1), border: pts[0] })
    }
    const cable = this.ids.get(key)!
    this.log = []
    for (const [a, c] of marks) this.mark(a, c, cable)
    this.logs.set(key, this.log)
    const t = this.tree(key)
    for (const { cells, border } of chains) {
      this.adopt(t, cells, t.parent.has(cells[0]) ? undefined : border)
      t.leaves.add(cells[cells.length - 1])
    }
    list.forEach((a, j) => this.routes.set(arcKey(a), paths[j]!))
    return true
  }

  /** Whether a node other than the arc's own ends now sits on its prior path. */
  private runOver(a: Arc, pts: Pt[] | undefined) {
    if (!pts) return true
    const g = this.grid
    const own = [this.nodes.get(a.state)!.index, this.nodes.get(a.verb)!.index]
    for (let j = 1; j < pts.length; j++) {
      const p = pts[j - 1]
      const q = pts[j]
      const n = Math.max(1, Math.ceil((Math.abs(q.x - p.x) + Math.abs(q.y - p.y)) / PITCH))
      for (let s = 0; s <= n; s++) {
        const o = g.owner[cellAt(g, p.x + ((q.x - p.x) * s) / n, p.y + ((q.y - p.y) * s) / n)]
        if (o !== FREE && o !== own[0] && o !== own[1]) return true
      }
    }
    return false
  }

  private tree(key: string): Tree {
    let t = this.trees.get(key)
    if (!t) {
      t = { parent: new Map(), rootPort: new Map(), leaves: new Set() }
      this.trees.set(key, t)
    }
    return t
  }

  private adopt(t: Tree, cells: number[], root: Pt | undefined) {
    for (let j = 0; j < cells.length; j++) {
      const c = cells[j]
      if (t.parent.has(c)) continue
      t.parent.set(c, j === 0 ? -1 : cells[j - 1])
      if (j === 0 && root) t.rootPort.set(c, root)
      if (t === this.active) this.mine[c] = 1
    }
  }

  private routeVia(a: Arc, cable: number): Pt[] | undefined {
    const { grid, search } = this
    const sPorts = this.portsOf(a.state, false)
    const vPorts = this.portsOf(a.verb, a.kind === 'give')
    const via = a.via!.map((p) => cellAt(grid, p.x, p.y))
    let starts: Start[] = sPorts.map((p) => ({ cell: p.cell, dir: p.out, cost: p.cost }))
    const cells: number[] = []
    const dirs: number[] = []
    for (let j = 0; j <= via.length; j++) {
      const last = j === via.length
      const found =
        search.run(cable, starts, last ? portTarget(grid, vPorts, cable, false) : cellTarget(grid, via[j]), null, false) ??
        search.run(cable, starts, last ? portTarget(grid, vPorts, cable, true) : cellTarget(grid, via[j]), null, true)
      if (!found) return undefined
      cells.push(...(cells.length ? found.cells.slice(1) : found.cells))
      dirs.push(...(dirs.length ? found.dirs.slice(1) : found.dirs))
      starts = [{ cell: found.cells[found.cells.length - 1], dir: found.dirs[found.dirs.length - 1], cost: 0 }]
    }
    const head = pickPort(sPorts, cells[0], dirs[0])
    const tail = pickPort(vPorts, cells[cells.length - 1], dirs[dirs.length - 1])
    this.occupy(cable, cells, dirs, head?.out, tail?.out)
    const t = this.tree(cableKey(a))
    this.adopt(t, cells, head?.border)
    t.leaves.add(cells[cells.length - 1])
    const pts = (head ? [head.border] : []).concat(cells.map((c) => ptOf(grid, c)))
    if (tail) pts.push(tail.border)
    return pts.map((p) => {
      const v = a.via!.find((q) => Math.abs(q.x - p.x) <= PITCH / 2 && Math.abs(q.y - p.y) <= PITCH / 2)
      return v ? { x: v.x, y: v.y } : p
    })
  }

  /** Routes the cable's arcs, or only those in `only`, branching from whatever of its tree is already laid. */
  routeCable(key: string, only?: Set<ArcKey>) {
    const { grid, search, nodes } = this
    const cable = this.ids.get(key)!
    const all = this.cables.get(key)!
    const list = only ? all.filter((a) => only.has(arcKey(a))) : all
    this.log = this.logs.get(key) ?? []
    const t = this.tree(key)
    this.active = t
    for (const c of t.parent.keys()) this.mine[c] = 1
    for (const a of list) {
      if (!a.via?.length) continue
      const pts = this.routeVia(a, cable) ?? [nodes.get(a.state)!.shape, ...a.via, nodes.get(a.verb)!.shape].map((p) => ({ x: p.x, y: p.y }))
      this.routes.set(arcKey(a), simplify(pts))
    }
    const state = nodes.get(all[0].state)!
    const sPorts = this.portsOf(state.id, false)
    const near = (a: Arc) => {
      const v = nodes.get(a.verb)!.shape
      return Math.abs(v.x - state.shape.x) + Math.abs(v.y - state.shape.y)
    }
    const auto = list.filter((a) => !a.via?.length).sort((a, b) => near(a) - near(b) || (a.verb < b.verb ? -1 : 1))
    for (const a of auto) {
      const vPorts = this.portsOf(a.verb, a.kind === 'give')
      const starts: Start[] = []
      for (const c of t.parent.keys()) if (!t.leaves.has(c)) for (let d = 0; d < 4; d++) starts.push({ cell: c, dir: d, cost: 0 })
      const spare = t.parent.size ? SPARE_PORT : 0
      for (const p of sPorts) if (!this.mine[p.cell]) starts.push({ cell: p.cell, dir: p.out, cost: p.cost + spare })
      const found =
        vPorts.length && starts.length
          ? (search.run(cable, starts, portTarget(grid, vPorts, cable, false), this.mine, false) ??
            search.run(cable, starts, portTarget(grid, vPorts, cable, true), this.mine, true))
          : undefined
      if (!found) {
        this.routes.set(arcKey(a), straight(state.shape, nodes.get(a.verb)!.shape))
        continue
      }
      const first = found.cells[0]
      const fromTree = t.parent.has(first)
      const head = fromTree ? undefined : pickPort(sPorts, first, found.dirs[0])
      const tail = pickPort(vPorts, found.cells[found.cells.length - 1], found.dirs[found.dirs.length - 1])
      this.occupy(cable, found.cells, found.dirs, head?.out, tail?.out)
      this.adopt(t, found.cells, head?.border)
      t.leaves.add(found.cells[found.cells.length - 1])
      const trunk: number[] = []
      for (let c = t.parent.get(first)!; c >= 0; c = t.parent.get(c)!) trunk.push(c)
      trunk.reverse()
      const root = t.rootPort.get(trunk.length ? trunk[0] : first) ?? head?.border
      const pts = (root ? [root] : []).concat([...trunk, ...found.cells].map((c) => ptOf(grid, c)))
      if (tail) pts.push(tail.border)
      this.routes.set(arcKey(a), simplify(pts))
    }
    this.logs.set(key, this.log)
    for (const c of t.parent.keys()) this.mine[c] = 0
    this.active = undefined
  }
}

const pickPort = (ports: Port[], cell: number, dir: number) => {
  let best: Port | undefined
  for (const p of ports) if (p.cell === cell && (!best || (back(p.out) === dir && back(best.out) !== dir))) best = p
  return best
}

const DRAG_GREED = 3
const DRAG_BUDGET = 12000

/** The first pass routes cheaply; the second rips each cable up and routes it again knowing where the rest went. */
const FIRST_CROSS = 10

/**
 * Routes every arc as an orthogonal polyline from the state's border to the verb's border.
 * Arcs with `via` pass through their points in order; the rest are grouped into cables (one state, one kind)
 * and grown as a tree from the state, so siblings share a trunk. Different cables never share a grid edge,
 * so they run as parallel tracks at least one pitch apart.
 *
 * With a `prior`, only arcs touching a moved node, or now run over by one, are routed again, as branches off
 * whatever of their cable still stands; the rest keep their prior paths. That is cheap enough for every frame of
 * a drag. Without one, every cable is routed, then ripped up and routed again.
 */
/** Past this many arcs the router's passes take minutes, so every arc is drawn straight, through its bend points. */
export const STRAIGHT_ABOVE = 4000

const straightRoutes = (net: Net, shapes: Map<string, Shape>): Map<ArcKey, Pt[]> => {
  const out = new Map<ArcKey, Pt[]>()
  for (const a of net.arcs) {
    const s = shapes.get(a.state)
    const v = shapes.get(a.verb)
    if (!s || !v) continue
    const via = a.via ?? []
    out.set(arcKey(a), [borderPoint(s, via[0] ?? v), ...via, borderPoint(v, via[via.length - 1] ?? s)])
  }
  return out
}

export function routeArcs(net: Net, shapes: Map<string, Shape>, prior?: Prior): Map<ArcKey, Pt[]> {
  if (net.arcs.length > STRAIGHT_ABOVE) return straightRoutes(net, shapes)
  const r = new Router(net, shapes)
  if (prior) {
    const todo: [string, Set<ArcKey> | undefined][] = []
    for (const k of r.order) {
      const list = r.cables.get(k)!
      if (prior.moved.has(list[0].state)) {
        todo.push([k, undefined])
        continue
      }
      const stale = new Set(list.filter((a) => prior.moved.has(a.verb) || !prior.routes.has(arcKey(a))).map(arcKey))
      if (!r.replay(k, prior.routes, stale)) todo.push([k, undefined])
      else if (stale.size) todo.push([k, stale])
    }
    r.tune(CROSS, DRAG_GREED, DRAG_BUDGET)
    for (const [k, only] of todo) r.routeCable(k, only)
    return r.routes
  }
  r.tune(FIRST_CROSS, GREED)
  for (const k of r.order) r.routeCable(k)
  r.tune(CROSS, GREED)
  for (const k of r.order) {
    r.release(k)
    r.routeCable(k)
  }
  return r.routes
}

export interface Junction {
  at: Pt
  /** the arcs whose routes pass through the junction */
  arcs: ArcKey[]
}

/** Points where a cable splits: a point that one cable leaves in three or more directions. */
export function cableJunctions(net: Net, routes: Map<ArcKey, Pt[]>): Junction[] {
  const byCable = new Map<string, ArcKey[]>()
  for (const a of net.arcs)
    if (routes.has(arcKey(a))) {
      const k = cableKey(a)
      const list = byCable.get(k)
      if (list) list.push(arcKey(a))
      else byCable.set(k, [arcKey(a)])
    }
  const out: Junction[] = []
  for (const keys of byCable.values()) {
    if (keys.length < 2) continue
    const bits = new Map<number, number>()
    const through = new Map<number, number[]>()
    const at = (x: number, y: number) => Math.round(x * 2) * 1e6 + Math.round(y * 2)
    keys.forEach((key, n) => {
      const pts = routes.get(key)!
      for (let j = 1; j < pts.length; j++) {
        const p = pts[j - 1]
        const q = pts[j]
        if (p.x !== q.x && p.y !== q.y) continue
        const len = Math.abs(q.x - p.x) + Math.abs(q.y - p.y)
        if (!len) continue
        const fwd = q.x > p.x ? 1 : q.x < p.x ? 4 : q.y > p.y ? 2 : 8
        const rev = q.x > p.x ? 4 : q.x < p.x ? 1 : q.y > p.y ? 8 : 2
        const steps = Math.max(1, Math.round(len / PITCH))
        for (let s = 0; s <= steps; s++) {
          const k = at(p.x + (q.x - p.x) * (s / steps), p.y + (q.y - p.y) * (s / steps))
          bits.set(k, (bits.get(k) ?? 0) | (s < steps ? fwd : 0) | (s > 0 ? rev : 0))
          const t = through.get(k)
          if (!t) through.set(k, [n])
          else if (t[t.length - 1] !== n) t.push(n)
        }
      }
    })
    for (const [k, b] of bits) {
      if (b !== 7 && b !== 11 && b !== 13 && b !== 14 && b !== 15) continue
      const x2 = Math.round(k / 1e6)
      out.push({ at: { x: x2 / 2, y: (k - x2 * 1e6) / 2 }, arcs: through.get(k)!.map((n) => keys[n]) })
    }
  }
  return out
}

/**
 * What changed between a routed net and the current one: nodes whose shape moved or resized, and the states of
 * arcs whose hand-placed points changed. Cables touching them are routed again; the rest keep their paths.
 */
export const priorFor = (before: { shapes: Map<string, Shape>; net: Net; routes: Map<ArcKey, Pt[]> }, net: Net, shapes: Map<string, Shape>): Prior => {
  const moved = new Set<string>()
  for (const [id, s] of shapes) {
    const o = before.shapes.get(id)
    if (!o || o.x !== s.x || o.y !== s.y || (o.kind === 'rect' && s.kind === 'rect' && o.w !== s.w)) moved.add(id)
  }
  const was = new Map(before.net.arcs.map((a) => [arcKey(a), a]))
  for (const a of net.arcs) {
    const o = was.get(arcKey(a))
    if (!o || JSON.stringify(o.via ?? null) !== JSON.stringify(a.via ?? null)) moved.add(a.state)
  }
  return { routes: before.routes, moved }
}

/** The point a fraction `t` of the way along a polyline, by length. */
export const pointAlong = (pts: Pt[], t: number): Pt => {
  let total = 0
  for (let i = 1; i < pts.length; i++) total += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)
  let left = Math.max(0, Math.min(1, t)) * total
  for (let i = 1; i < pts.length; i++) {
    const len = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y)
    if (left <= len && len > 0) return { x: pts[i - 1].x + ((pts[i].x - pts[i - 1].x) * left) / len, y: pts[i - 1].y + ((pts[i].y - pts[i - 1].y) * left) / len }
    left -= len
  }
  return pts[pts.length - 1]
}

/**
 * Where an arc's count badge goes: the middle of the longest stretch of its route that no cable-mate runs along, kept
 * off the end markers, so the count can't be read as a mate's. When the arc's own stretch is only its end stub, the badge goes there anyway.
 */
const cableIndex = new WeakMap<Net, Map<string, Arc[]>>()
const cablesOf = (net: Net) => {
  let index = cableIndex.get(net)
  if (!index) {
    index = new Map()
    for (const a of net.arcs) {
      const k = cableKey(a)
      const list = index.get(k)
      if (list) list.push(a)
      else index.set(k, [a])
    }
    cableIndex.set(net, index)
  }
  return index
}

export const countBadgeAt = (net: Net, routes: Map<ArcKey, Pt[]>, arc: Arc): Pt => {
  const own = routes.get(arcKey(arc))!
  const mates = (cablesOf(net).get(cableKey(arc)) ?? []).filter((b) => arcKey(b) !== arcKey(arc)).map((b) => routes.get(arcKey(b)) ?? [])
  const total = own.slice(1).reduce((n, q, i) => n + Math.hypot(q.x - own[i].x, q.y - own[i].y), 0)
  const ENDS = 12
  const BADGE_W = 16
  let best = { from: 0, to: 0 }
  let unclipped = { from: 0, to: 0 }
  let run = 0
  for (let i = 1; i < own.length; i++) {
    const [p, q] = [own[i - 1], own[i]]
    const len = Math.hypot(q.x - p.x, q.y - p.y)
    const horizontal = p.y === q.y
    const covered: [number, number][] = []
    if (horizontal || p.x === q.x)
      for (const m of mates)
        for (let j = 1; j < m.length; j++) {
          const [r, s] = [m[j - 1], m[j]]
          const on = horizontal ? r.y === p.y && s.y === p.y : r.x === p.x && s.x === p.x
          if (!on) continue
          const along = (t: Pt) => (horizontal ? (t.x - p.x) * Math.sign(q.x - p.x) : (t.y - p.y) * Math.sign(q.y - p.y))
          covered.push([Math.min(along(r), along(s)), Math.max(along(r), along(s))])
        }
    covered.sort((a, b) => a[0] - b[0])
    let at = 0
    const free = (lo: number, hi: number) => {
      if (hi - lo > unclipped.to - unclipped.from) unclipped = { from: run + lo, to: run + hi }
      const from = Math.max(run + lo, ENDS)
      const to = Math.min(run + hi, total - ENDS)
      if (to - from > best.to - best.from) best = { from, to }
    }
    for (const [lo, hi] of covered) {
      if (lo > at) free(at, Math.min(lo, len))
      at = Math.max(at, hi)
    }
    if (at < len) free(at, len)
    run += len
  }
  const at = best.to - best.from >= BADGE_W ? best : unclipped
  return pointAlong(own, at.to > at.from ? (at.from + at.to) / 2 / total : 0.5)
}

/** SVG path for a polyline with its corners rounded. */
export const polylinePath = (pts: Pt[], radius = 4) => {
  let d = `M${pts[0].x},${pts[0].y}`
  for (let i = 1; i < pts.length - 1; i++) {
    const [a, b, c] = [pts[i - 1], pts[i], pts[i + 1]]
    const l1 = Math.hypot(b.x - a.x, b.y - a.y)
    const l2 = Math.hypot(c.x - b.x, c.y - b.y)
    const r = Math.min(radius, l1 / 2, l2 / 2)
    if (r < 0.5) {
      d += ` L${b.x},${b.y}`
      continue
    }
    d += ` L${b.x + ((a.x - b.x) * r) / l1},${b.y + ((a.y - b.y) * r) / l1} Q${b.x},${b.y} ${b.x + ((c.x - b.x) * r) / l2},${b.y + ((c.y - b.y) * r) / l2}`
  }
  const z = pts[pts.length - 1]
  return `${d} L${z.x},${z.y}`
}
