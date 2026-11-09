import { WORLD, isIdent, type Arc, type ArcKind, type Net, type Point, type State, type Seat, type Verb } from './model'
import type { Shape } from './geometry'
import { PITCH, arcKey, cableKey } from './route'

export type NodeKind = 'state' | 'verb'
export interface NodeRef {
  kind: NodeKind
  id: string
}
export interface ArcRef {
  kind: 'arc'
  state: string
  verb: string
  arcKind: ArcKind
}
export type Selection = NodeRef | ArcRef | { kind: 'group'; id: string } | null

export const sameArc = (a: Arc, r: ArcRef) => a.state === r.state && a.verb === r.verb && a.kind === r.arcKind
export const arcRef = (a: Arc): ArcRef => ({ kind: 'arc', state: a.state, verb: a.verb, arcKind: a.kind })

export const GRID = 10
export const snap = (n: number) => Math.round(n / GRID) * GRID

const takenIds = (net: Net) => new Set([...net.states, ...net.verbs, ...net.seats].map((n) => n.id).concat(WORLD))

export const uniqueId = (taken: Set<string>, prefix: string) => {
  let i = 1
  while (taken.has(`${prefix}_${i}`)) i++
  return `${prefix}_${i}`
}

export const addState = (net: Net, x: number, y: number): [Net, string] => {
  const id = uniqueId(takenIds(net), 'state')
  const p: State = { id, label: `State ${id.slice(6)}`, marks: 0, seenBy: 'all', x: snap(x), y: snap(y) }
  return [{ ...net, states: [...net.states, p] }, id]
}

export const addVerb = (net: Net, x: number, y: number): [Net, string] => {
  const id = uniqueId(takenIds(net), 'verb')
  const v: Verb = { id, label: `Verb ${id.slice(5)}`, by: net.seats[0]?.id ?? WORLD, priority: 0, weight: 1, x: snap(x), y: snap(y) }
  return [{ ...net, verbs: [...net.verbs, v] }, id]
}

export const moveNodes = (net: Net, origins: Map<string, { x: number; y: number }>, dx: number, dy: number, snapEach: boolean): Net => {
  const at = <T extends { id: string; x: number; y: number }>(n: T): T => {
    const o = origins.get(n.id)
    if (!o) return n
    return snapEach ? { ...n, x: snap(o.x + dx), y: snap(o.y + dy) } : { ...n, x: o.x + snap(dx), y: o.y + snap(dy) }
  }
  return { ...net, states: net.states.map(at), verbs: net.verbs.map(at) }
}

/** Bipartite by construction: a state can only meet a verb. */
export const connect = (net: Net, from: NodeRef, to: NodeRef): [Net, ArcRef] | null => {
  if (from.kind === to.kind) return null
  const arc: Arc =
    from.kind === 'state' ? { kind: 'take', state: from.id, verb: to.id, count: 1 } : { kind: 'give', state: to.id, verb: from.id, count: 1 }
  if (net.arcs.some((a) => a.state === arc.state && a.verb === arc.verb && a.kind === arc.kind)) return null
  return [{ ...net, arcs: [...net.arcs, arc] }, arcRef(arc)]
}

export const deleteSelection = (net: Net, sel: Selection): Net => {
  if (!sel) return net
  switch (sel.kind) {
    case 'state':
      return { ...net, states: net.states.filter((p) => p.id !== sel.id), arcs: net.arcs.filter((a) => a.state !== sel.id) }
    case 'verb':
      return { ...net, verbs: net.verbs.filter((v) => v.id !== sel.id), arcs: net.arcs.filter((a) => a.verb !== sel.id) }
    case 'arc':
      return { ...net, arcs: net.arcs.filter((a) => !sameArc(a, sel)) }
    case 'group':
      return deleteGroup(net, sel.id)
  }
}

export const updateState = (net: Net, id: string, patch: Partial<State>): Net => ({
  ...net,
  states: net.states.map((p) => (p.id === id ? { ...p, ...patch } : p)),
})

export const updateVerb = (net: Net, id: string, patch: Partial<Verb>): Net => ({
  ...net,
  verbs: net.verbs.map((v) => (v.id === id ? { ...v, ...patch } : v)),
})

/** Returns null when the change would duplicate an existing arc. */
export const updateArc = (net: Net, ref: ArcRef, patch: Partial<Pick<Arc, 'kind' | 'count'>>): [Net, ArcRef] | null => {
  const old = net.arcs.find((a) => sameArc(a, ref))
  if (!old) return null
  const next = { ...old, ...patch }
  if (next.kind !== old.kind && net.arcs.some((a) => a.state === next.state && a.verb === next.verb && a.kind === next.kind)) return null
  return [{ ...net, arcs: net.arcs.map((a) => (a === old ? next : a)) }, arcRef(next)]
}

export const validateNewId = (net: Net, oldId: string, newId: string): string | undefined => {
  if (newId === oldId) return undefined
  if (!isIdent(newId)) return 'lowercase letters, digits and _ only, starting with a letter'
  if (takenIds(net).has(newId)) return `"${newId}" is already taken`
  return undefined
}

export const renameNode = (net: Net, ref: NodeRef, newId: string): Net => {
  const r = <T extends { id: string }>(n: T) => (n.id === ref.id ? { ...n, id: newId } : n)
  return ref.kind === 'state'
    ? { ...net, states: net.states.map(r), arcs: net.arcs.map((a) => (a.state === ref.id ? { ...a, state: newId } : a)) }
    : { ...net, verbs: net.verbs.map(r), arcs: net.arcs.map((a) => (a.verb === ref.id ? { ...a, verb: newId } : a)) }
}

const SEAT_COLORS = ['#e4572e', '#2e86ab', '#7b2cbf', '#3a9d5d', '#d4a017', '#c2457a', '#4f6d7a']

export const addSeat = (net: Net): Net => {
  const id = uniqueId(takenIds(net), 'seat')
  const color = SEAT_COLORS.find((c) => !net.seats.some((s) => s.color === c)) ?? SEAT_COLORS[net.seats.length % SEAT_COLORS.length]
  return { ...net, seats: [...net.seats, { id, name: `Seat ${id.slice(5)}`, color }] }
}

export const updateSeat = (net: Net, id: string, patch: Partial<Seat>): Net => {
  const newId = patch.id ?? id
  return {
    ...net,
    seats: net.seats.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    verbs: newId === id ? net.verbs : net.verbs.map((v) => (v.by === id ? { ...v, by: newId } : v)),
    states: newId === id ? net.states : net.states.map((p) => (p.seenBy === 'all' ? p : { ...p, seenBy: p.seenBy.map((s) => (s === id ? newId : s)) })),
  }
}

/** A deleted seat's verbs fall to the world rather than vanishing, so no arcs are lost. */
export const deleteSeat = (net: Net, id: string): Net => ({
  ...net,
  seats: net.seats.filter((s) => s.id !== id),
  verbs: net.verbs.map((v) => (v.by === id ? { ...v, by: WORLD } : v)),
  states: net.states.map((p) => (p.seenBy === 'all' ? p : { ...p, seenBy: p.seenBy.filter((s) => s !== id) })),
})

export const addGroup = (net: Net): Net => {
  const id = uniqueId(new Set(net.groups.map((g) => g.id)), 'group')
  return { ...net, groups: [...net.groups, { id, label: `Group ${id.slice(6)}` }] }
}

export const updateGroup = (net: Net, id: string, patch: { id?: string; label?: string }): Net => {
  const newId = patch.id ?? id
  const regroup = <T extends { group?: string }>(n: T) => (n.group === id ? { ...n, group: newId } : n)
  return {
    ...net,
    groups: net.groups.map((g) => (g.id === id ? { ...g, ...patch } : g)),
    states: net.states.map(regroup),
    verbs: net.verbs.map(regroup),
  }
}

export const deleteGroup = (net: Net, id: string): Net => {
  const ungroup = <T extends { group?: string }>(n: T): T => (n.group === id ? { ...n, group: undefined } : n)
  return { ...net, groups: net.groups.filter((g) => g.id !== id), states: net.states.map(ungroup), verbs: net.verbs.map(ungroup) }
}

const outside = (s: Shape, p: Point, pad: number) =>
  s.kind === 'circle' ? Math.hypot(p.x - s.x, p.y - s.y) > s.r + pad : Math.abs(p.x - s.x) > s.w / 2 + pad || Math.abs(p.y - s.y) > s.h / 2 + pad

const dropStraight = (pts: Point[]) =>
  pts.filter((p, i) => {
    if (i === 0 || i === pts.length - 1) return true
    const a = pts[i - 1]
    const b = pts[i + 1]
    return Math.abs((p.x - a.x) * (b.y - p.y) - (p.y - a.y) * (b.x - p.x)) > 1e-6
  })

const onLine = (p: Point, q: Point, r: Point, s: Point) => {
  const horizontal = Math.abs(p.y - q.y) < 0.5
  if (horizontal ? Math.abs(r.y - s.y) >= 0.5 || Math.abs(r.y - p.y) >= 0.5 : Math.abs(r.x - s.x) >= 0.5 || Math.abs(r.x - p.x) >= 0.5) return false
  const along = horizontal ? (t: Point) => t.x : (t: Point) => t.y
  const lo = Math.max(Math.min(along(p), along(q)), Math.min(along(r), along(s)))
  const hi = Math.min(Math.max(along(p), along(q)), Math.max(along(r), along(s)))
  return hi - lo > 1
}

/**
 * Slides one segment of an arc's route sideways and stores the result as `via`. Every arc of the same cable that
 * runs along that segment moves with it, so dragging a shared trunk moves the trunk.
 */
export const moveSegment = (net: Net, routes: Map<string, Point[]>, shapes: Map<string, Shape>, ref: ArcRef, seg: number, by: Point): Net => {
  const arc = net.arcs.find((a) => sameArc(a, ref))
  const pts = arc && routes.get(arcKey(arc))
  if (!arc || !pts || seg < 0 || seg + 1 >= pts.length) return net
  const [p, q] = [pts[seg], pts[seg + 1]]
  const horizontal = Math.abs(p.y - q.y) < 0.5
  const vertical = Math.abs(p.x - q.x) < 0.5
  const shift = horizontal ? { x: 0, y: snap5(by.y) } : vertical ? { x: snap5(by.x), y: 0 } : { x: snap5(by.x), y: snap5(by.y) }
  if (!shift.x && !shift.y) return net
  const viaFor = (a: Arc): Point[] | undefined => {
    const r = routes.get(arcKey(a))
    if (!r) return undefined
    const j = a === arc ? seg : r.findIndex((s, i) => i + 1 < r.length && (horizontal || vertical) && onLine(p, q, s, r[i + 1]))
    if (j < 0) return undefined
    const moved = r.map((t, i) => (i === j || i === j + 1 ? { x: t.x + shift.x, y: t.y + shift.y } : t))
    const via = moved.slice(1, -1)
    if (j === 0 && outside(shapes.get(a.state)!, moved[0], 6)) via.unshift(moved[0])
    if (j + 1 === r.length - 1 && outside(shapes.get(a.verb)!, moved[moved.length - 1], 6)) via.push(moved[moved.length - 1])
    const snapped = via.map((t) => ({ x: snap5(t.x), y: snap5(t.y) }))
    return dropStraight(snapped).filter((t, i, all) => i === 0 || t.x !== all[i - 1].x || t.y !== all[i - 1].y)
  }
  const cable = cableKey(arc)
  return {
    ...net,
    arcs: net.arcs.map((a) => {
      if (cableKey(a) !== cable) return a
      const via = viaFor(a)
      return via ? { ...a, via } : a
    }),
  }
}

const snap5 = (n: number) => Math.round(n / PITCH) * PITCH

/** Returns the given arcs, or every arc, to automatic routing. */
export const autoRoute = (net: Net, which?: ArcRef[]): Net => ({
  ...net,
  arcs: net.arcs.map((a) => {
    if (!a.via || (which && !which.some((r) => sameArc(a, r)))) return a
    const { via: _, ...rest } = a
    return rest
  }),
})
