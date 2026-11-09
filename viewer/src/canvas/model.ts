export const WORLD = 'world' as const

export type SeatId = string
export type Speaker = typeof WORLD | SeatId

export interface Seat {
  id: SeatId
  name: string
  color: string
}

export interface Group {
  id: string
  label: string
}

export interface State {
  id: string
  label: string
  marks: number
  seenBy: 'all' | SeatId[]
  ends?: string
  group?: string
  x: number
  y: number
  /** A Record's radius, sized to hold its fields. */
  r?: number
  /** A Record's fields, one line each, written inside its place. */
  lines?: string[]
}

export interface Verb {
  id: string
  label: string
  by: Speaker
  priority: number
  weight: number
  group?: string
  x: number
  y: number
}

export type ArcKind = 'take' | 'give' | 'need' | 'unless'

export interface Point {
  x: number
  y: number
}

export interface Arc {
  kind: ArcKind
  state: string
  verb: string
  count: number
  /** Bend points set by hand, listed from the state end to the verb end. Absent means the editor routes the arc. */
  via?: Point[]
}

export interface Net {
  title: string
  seats: Seat[]
  groups: Group[]
  states: State[]
  verbs: Verb[]
  arcs: Arc[]
}

export type Marking = Record<string, number>

export const ARC_KINDS: readonly ArcKind[] = ['take', 'give', 'need', 'unless']

export const emptyNet = (): Net => ({ title: 'Untitled', seats: [], groups: [], states: [], verbs: [], arcs: [] })

export const initialMarking = (net: Net): Marking =>
  Object.fromEntries(net.states.map((p) => [p.id, p.marks]))

export const isIdent = (s: string) => /^[a-z][a-z0-9_]*$/.test(s)
