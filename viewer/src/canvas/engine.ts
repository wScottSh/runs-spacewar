import { WORLD, type Marking, type Net, type State, type SeatId, type Speaker, type Verb } from './model'

export interface Compiled {
  net: Net
  inputs: Map<string, { state: string; kind: 'take' | 'need' | 'unless'; count: number }[]>
  outputs: Map<string, { state: string; count: number }[]>
  outcomes: State[]
  /** Each verb is filed under one state it takes or needs, so only verbs under a marked state can be possible. */
  byKeyState: Map<string, number[]>
  /** Verbs with nothing to take or need: they are checked at every marking. */
  unkeyed: number[]
}

export const compile = (net: Net): Compiled => {
  const inputs: Compiled['inputs'] = new Map(net.verbs.map((v) => [v.id, []]))
  const outputs: Compiled['outputs'] = new Map(net.verbs.map((v) => [v.id, []]))
  for (const a of net.arcs) {
    if (a.kind === 'give') outputs.get(a.verb)?.push({ state: a.state, count: a.count })
    else inputs.get(a.verb)?.push({ state: a.state, kind: a.kind, count: a.count })
  }
  const byKeyState: Compiled['byKeyState'] = new Map()
  const unkeyed: number[] = []
  net.verbs.forEach((v, i) => {
    const key = inputs.get(v.id)!.find((a) => a.kind !== 'unless')
    if (!key) unkeyed.push(i)
    else byKeyState.set(key.state, [...(byKeyState.get(key.state) ?? []), i])
  })
  return { net, inputs, outputs, outcomes: net.states.filter((p) => p.ends !== undefined), byKeyState, unkeyed }
}

export const isEnabled = (c: Compiled, m: Marking, verb: string): boolean =>
  c.inputs.get(verb)!.every(({ state, kind, count }) =>
    kind === 'unless' ? (m[state] ?? 0) < count : (m[state] ?? 0) >= count,
  )

export const fire = (c: Compiled, m: Marking, verb: string): Marking => {
  const next = { ...m }
  for (const { state, kind, count } of c.inputs.get(verb)!) if (kind === 'take') next[state] = (next[state] ?? 0) - count
  for (const { state, count } of c.outputs.get(verb)!) next[state] = (next[state] ?? 0) + count
  return next
}

/** Every marked outcome state counts, so a shared victory is two outcome states marked at once. */
export const outcomeOf = (c: Compiled, m: Marking): string | undefined => {
  const ends = c.outcomes.filter((p) => (m[p.id] ?? 0) > 0).map((p) => p.ends!)
  return ends.length ? ends.join(' and ') : undefined
}

export interface ChanceBranch {
  verb: Verb
  p: number
}

export type Turn =
  | { kind: 'over'; outcome: string }
  | { kind: 'world'; branches: ChanceBranch[] }
  | { kind: 'seats'; choices: Map<SeatId, Verb[]> }
  | { kind: 'stalled' }

/**
 * The conversation: when the world has something to say it speaks first, highest
 * priority first, ties broken by chance in proportion to weight. Only when the
 * world falls silent do the seats get to choose.
 */
export const whoseTurn = (c: Compiled, m: Marking): Turn => {
  const outcome = outcomeOf(c, m)
  if (outcome !== undefined) return { kind: 'over', outcome }
  const candidates = [...c.unkeyed]
  for (const id in m) if (m[id] > 0) candidates.push(...(c.byKeyState.get(id) ?? []))
  const enabled = candidates
    .sort((a, b) => a - b)
    .map((i) => c.net.verbs[i])
    .filter((v) => isEnabled(c, m, v.id))
  const world = enabled.filter((v) => v.by === WORLD)
  if (world.length) {
    const top = Math.max(...world.map((v) => v.priority))
    const tier = world.filter((v) => v.priority === top)
    const total = tier.reduce((s, v) => s + v.weight, 0)
    return { kind: 'world', branches: tier.map((verb) => ({ verb, p: verb.weight / total })) }
  }
  const choices = new Map<SeatId, Verb[]>()
  for (const v of enabled) choices.set(v.by, [...(choices.get(v.by) ?? []), v])
  return choices.size ? { kind: 'seats', choices } : { kind: 'stalled' }
}

export interface Utterance {
  speaker: Speaker
  verb: string
  p?: number
}

export const WORLD_LIMIT = 10_000

/** Let the world respond until it falls silent. Returns the settled marking and what was said. */
export const settle = (c: Compiled, m: Marking, rand: () => number = Math.random) => {
  const said: Utterance[] = []
  let turn = whoseTurn(c, m)
  while (turn.kind === 'world') {
    if (said.length >= WORLD_LIMIT) throw new Error(`the world answered ${WORLD_LIMIT} times without falling silent`)
    let r = rand()
    const pick = turn.branches.find((b) => (r -= b.p) < 0) ?? turn.branches[turn.branches.length - 1]
    m = fire(c, m, pick.verb.id)
    said.push({ speaker: WORLD, verb: pick.verb.id, p: turn.branches.length > 1 ? pick.p : undefined })
    turn = whoseTurn(c, m)
  }
  return { marking: m, said, turn }
}

export const canSee = (state: State, seat: SeatId | undefined) =>
  seat === undefined || state.seenBy === 'all' || state.seenBy.includes(seat)

/**
 * What a seat hears of an utterance. Saying a verb is public, but a verb that touches a state
 * the listener cannot see is heard only as "<speaker> acted", so a covered coin stays covered.
 */
export const heardBy = (c: Compiled, u: Utterance, seat: SeatId | undefined): string | undefined => {
  const byId = new Map(c.net.states.map((p) => [p.id, p]))
  const touched = [...c.inputs.get(u.verb)!.map((a) => a.state), ...c.outputs.get(u.verb)!.map((a) => a.state)]
  return touched.every((p) => canSee(byId.get(p)!, seat)) ? u.verb : undefined
}

export type ReplayResult = { ok: true; marking: Marking; turn: Turn } | { ok: false; at: number; reason: string }

/**
 * Check that a transcript is a legal conversation of this net. A RUNS game conforms to a MAPS
 * design when every transcript it produces replays here.
 */
export const replay = (c: Compiled, transcript: Utterance[], start: Marking): ReplayResult => {
  let m = start
  for (const [i, u] of transcript.entries()) {
    const turn = whoseTurn(c, m)
    const legal =
      turn.kind === 'world' ? turn.branches.some((b) => b.verb.id === u.verb) && u.speaker === WORLD
      : turn.kind === 'seats' ? (turn.choices.get(u.speaker) ?? []).some((v) => v.id === u.verb)
      : false
    if (!legal) return { ok: false, at: i, reason: `${u.speaker} cannot say ${u.verb} when the turn is ${turn.kind}` }
    m = fire(c, m, u.verb)
  }
  return { ok: true, marking: m, turn: whoseTurn(c, m) }
}

