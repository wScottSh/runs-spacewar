import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { canSee } from './engine'
import { WORLD, type Arc, type Marking, type Net, type SeatId } from './model'
import { addState, addVerb, arcRef, connect, deleteSelection, moveNodes, moveSegment, sameArc, snap, type ArcRef, type NodeRef, type Selection } from './edit'
import {
  DOTS,
  STATE_R,
  VERB_H,
  arrowAt,
  capAt,
  chanceTies,
  dieWidth,
  groupHulls,
  inflate,
  PRIORITY_R,
  priorityBadge,
  readableOn,
  shapeBox,
  shapesOf,
  union,
  verbWidth,
  type Box,
  type Pt,
  type Shape,
} from './geometry'
import { arcKey, cableJunctions, countBadgeAt, pointAlong, polylinePath, type ArcKey } from './route'
import { useRoutes } from './useRoutes'

export interface Flight {
  key: number
  frames: { verb: string; before: Marking; after: Marking }[]
}

export interface PlayView {
  marking: Marking
  viewer: SeatId | undefined
  legal: Set<string>
  waiting: Set<string>
  onSpeak: (verb: string) => void
  flight: Flight | undefined
}

interface Props {
  net: Net
  mode: 'edit' | 'play'
  selection: Selection
  onSelect: (s: Selection) => void
  onCommit: (net: Net, sel?: Selection) => void
  onCheckpoint: () => void
  onLive: (net: Net) => void
  play: PlayView | undefined
  fitKey: number
  /** phone layout: touch-sized handles, no page gestures on the canvas */
  touch?: boolean
}

interface View {
  x: number
  y: number
  k: number
}

type Gesture =
  | { kind: 'idle' }
  | { kind: 'pan'; sx: number; sy: number; from: View; moved: boolean; tap?: Selection }
  | { kind: 'drag'; start: Pt; base: Net; origins: Map<string, Pt>; snapEach: boolean; moved: boolean }
  | { kind: 'connect'; from: NodeRef }
  | { kind: 'route'; ref: ArcRef; seg: number; start: Pt; base: Net; routes: Map<ArcKey, Pt[]>; shapes: Map<string, Shape>; moved: boolean }
  | { kind: 'pinch'; d0: number; mid0: Pt; from: View }

type Tool = 'state' | 'verb' | null

const FRAME_MS = 280
/** The height of one field's line inside a Record. */
export const FIELD_LINE = 10
/** Nets with more nodes than this draw only what is on screen. */
const CULL_ABOVE = 3000
const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1
/** Shorter segments are port stubs and jogs: still draggable, but a grip on them would cover the arrowhead or the node. */
const GRIP_MIN = 16
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))

export function Canvas(props: Props) {
  const { net, mode, selection, onSelect, play } = props
  const wrap = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 })
  const [hover, setHover] = useState<NodeRef | null>(null)
  const [connectTo, setConnectTo] = useState<Pt | null>(null)
  const [tool, setTool] = useState<Tool>(null)
  const [cursor, setCursor] = useState<Pt | null>(null)
  const [panning, setPanning] = useState(false)
  const gesture = useRef<Gesture>({ kind: 'idle' })
  const space = useRef(false)
  const pointers = useRef(new Map<number, Pt>())
  const latest = useRef({ props, view, tool, cursor })
  latest.current = { props, view, tool, cursor }

  const chanceVerbs = useMemo(() => chanceTies(net), [net])
  const shapes = useMemo(() => shapesOf(net, chanceVerbs), [net, chanceVerbs])
  const hulls = useMemo(() => groupHulls(net, shapes), [net, shapes])
  const routes = useRoutes(net, shapes)
  const junctions = useMemo(() => cableJunctions(net, routes), [net, routes])
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const large = net.states.length + net.verbs.length > CULL_ABOVE
  /** On a large net only what is on screen is drawn; everything is drawn on a small one. */
  const onScreen = useMemo(() => {
    if (!large) return undefined
    const pad = 200 / view.k
    const box = { x0: -view.x / view.k - pad, y0: -view.y / view.k - pad, x1: (size.w - view.x) / view.k + pad, y1: (size.h - view.y) / view.k + pad }
    const ids = new Set<string>()
    for (const [id, sh] of shapes) if (overlaps(shapeBox(sh), box)) ids.add(id)
    return { ids, box }
  }, [large, shapes, view, size])
  const shown = (id: string) => !onScreen || onScreen.ids.has(id)

  const toWorld = (cx: number, cy: number, v = latest.current.view): Pt => {
    const r = svg.current!.getBoundingClientRect()
    return { x: (cx - r.left - v.x) / v.k, y: (cy - r.top - v.y) / v.k }
  }

  const fit = () => {
    const el = wrap.current
    if (!el) return
    // A large net fits to where play starts, the marked states, rather than shrinking the whole net to nothing.
    const start = large ? net.states.filter((p) => p.marks > 0).map((p) => shapes.get(p.id)!) : []
    const box = start.length ? inflate(union(start.map(shapeBox))!, 400) : union([...shapes.values()].map(shapeBox).concat(hulls.map((h) => h.box)))
    const { width, height } = el.getBoundingClientRect()
    if (!box) return setView({ x: width / 2, y: height / 2, k: 1 })
    const b = inflate(box, 48)
    const k = Math.min(width / (b.x1 - b.x0), height / (b.y1 - b.y0), 1.6)
    setView({ k, x: (width - (b.x1 - b.x0) * k) / 2 - b.x0 * k, y: (height - (b.y1 - b.y0) * k) / 2 - b.y0 * k })
  }
  useLayoutEffect(fit, [props.fitKey])

  // A node chosen from outside the canvas, such as a name in the details, is brought into view.
  const chosen = selection && 'id' in selection ? selection.id : null
  useEffect(() => {
    const sh = chosen ? shapes.get(chosen) : undefined
    const el = wrap.current
    if (!sh || !el) return
    const { width, height } = el.getBoundingClientRect()
    const v = latest.current.view
    const sx = sh.x * v.k + v.x
    const sy = sh.y * v.k + v.y
    if (sx > 40 && sx < width - 40 && sy > 40 && sy < height - 40) return
    setView({ k: v.k, x: width / 2 - sh.x * v.k, y: height / 3 - sh.y * v.k })
  }, [chosen])

  useEffect(() => {
    const el = svg.current!
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      const cx = e.clientX - r.left
      const cy = e.clientY - r.top
      setView((v) => {
        const k = Math.min(4, Math.max(0.15, v.k * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015))))
        return { k, x: cx - (cx - v.x) * (k / v.k), y: cy - (cy - v.y) * (k / v.k) }
      })
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [])

  useEffect(() => {
    const el = svg.current!
    const down = (e: PointerEvent) => {
      if (e.pointerType !== 'touch') return
      const r = el.getBoundingClientRect()
      pointers.current.set(e.pointerId, { x: e.clientX - r.left, y: e.clientY - r.top })
      if (pointers.current.size !== 2) return
      e.stopPropagation()
      const g = gesture.current
      const { props: p, view: v } = latest.current
      if (g.kind === 'drag' && g.moved) p.onLive(g.base)
      setConnectTo(null)
      const [a, b] = [...pointers.current.values()]
      gesture.current = { kind: 'pinch', d0: Math.hypot(a.x - b.x, a.y - b.y) || 1, mid0: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, from: v }
    }
    el.addEventListener('pointerdown', down, { capture: true })
    return () => el.removeEventListener('pointerdown', down, { capture: true })
  }, [])

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (pointers.current.has(e.pointerId)) {
        const r = svg.current!.getBoundingClientRect()
        pointers.current.set(e.pointerId, { x: e.clientX - r.left, y: e.clientY - r.top })
      }
      const g = gesture.current
      if (g.kind === 'pinch') {
        if (pointers.current.size < 2) return
        const [a, b] = [...pointers.current.values()]
        const k = Math.min(4, Math.max(0.15, (g.from.k * Math.hypot(a.x - b.x, a.y - b.y)) / g.d0))
        const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
        const wx = (g.mid0.x - g.from.x) / g.from.k
        const wy = (g.mid0.y - g.from.y) / g.from.k
        setView({ k, x: mid.x - wx * k, y: mid.y - wy * k })
        return
      }
      const { props: p, view: v } = latest.current
      if (g.kind === 'pan') {
        const dx = e.clientX - g.sx
        const dy = e.clientY - g.sy
        if (Math.hypot(dx, dy) > 3) g.moved = true
        setView({ ...g.from, x: g.from.x + dx, y: g.from.y + dy })
      } else if (g.kind === 'drag') {
        const w = toWorld(e.clientX, e.clientY, v)
        const dx = w.x - g.start.x
        const dy = w.y - g.start.y
        if (!g.moved && Math.hypot(dx, dy) * v.k < 3) return
        if (!g.moved) p.onCheckpoint()
        g.moved = true
        p.onLive(moveNodes(g.base, g.origins, dx, dy, g.snapEach))
      } else if (g.kind === 'route') {
        const w = toWorld(e.clientX, e.clientY, v)
        const by = { x: w.x - g.start.x, y: w.y - g.start.y }
        if (!g.moved && Math.hypot(by.x, by.y) * v.k < 3) return
        if (!g.moved) p.onCheckpoint()
        g.moved = true
        p.onLive(moveSegment(g.base, g.routes, g.shapes, g.ref, g.seg, by))
      } else if (g.kind === 'connect') setConnectTo(toWorld(e.clientX, e.clientY, v))
    }
    const up = (e: PointerEvent) => {
      pointers.current.delete(e.pointerId)
      const g = gesture.current
      if (g.kind === 'pinch') {
        if (pointers.current.size === 0) gesture.current = { kind: 'idle' }
        return
      }
      const { props: p } = latest.current
      if (g.kind === 'pan' && !g.moved) p.onSelect(g.tap ?? null)
      if (g.kind === 'connect') {
        const el = document.elementFromPoint(e.clientX, e.clientY)?.closest<SVGGElement>('[data-node]')
        const to = el && ({ kind: el.dataset.kind, id: el.dataset.node } as NodeRef)
        const made = to && connect(p.net, g.from, to)
        if (made) p.onCommit(made[0], made[1])
        setConnectTo(null)
      }
      gesture.current = { kind: 'idle' }
      setPanning(false)
    }
    const cancel = (e: PointerEvent) => {
      pointers.current.delete(e.pointerId)
      if (pointers.current.size === 0) {
        gesture.current = { kind: 'idle' }
        setConnectTo(null)
        setPanning(false)
      }
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
    }
  }, [])

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return
      if (e.key === ' ') {
        space.current = true
        setPanning(true)
        e.preventDefault()
        return
      }
      const { props: p, cursor: c, view: v } = latest.current
      if (p.mode !== 'edit' || e.ctrlKey || e.metaKey || e.altKey) return
      const at = c ?? centerOf(v)
      const k = e.key.toLowerCase()
      if (k === 's' || k === 'v') {
        const [next, id] = k === 's' ? addState(p.net, at.x, at.y) : addVerb(p.net, at.x, at.y)
        p.onCommit(next, { kind: k === 's' ? 'state' : 'verb', id })
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && p.selection) {
        e.preventDefault()
        p.onCommit(deleteSelection(p.net, p.selection), null)
      } else if (e.key === 'Escape') {
        setTool(null)
        p.onSelect(null)
      }
    }
    const keyUp = (e: KeyboardEvent) => {
      if (e.key === ' ') {
        space.current = false
        if (gesture.current.kind !== 'pan') setPanning(false)
      }
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', keyUp)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', keyUp)
    }
  }, [])

  const centerOf = (v: View): Pt => {
    const r = svg.current!.getBoundingClientRect()
    return { x: (r.width / 2 - v.x) / v.k, y: (r.height / 2 - v.y) / v.k }
  }

  /** On touch, pressing something unselected pans; a tap without movement selects it instead. */
  const startPan = (e: React.PointerEvent, tap?: Selection) => {
    gesture.current = { kind: 'pan', sx: e.clientX, sy: e.clientY, from: latest.current.view, moved: false, tap }
    setPanning(true)
  }

  const onBackgroundDown = (e: React.PointerEvent) => {
    if (e.button !== 0 && e.button !== 1) return
    if (mode === 'edit' && tool && !space.current) {
      const w = toWorld(e.clientX, e.clientY)
      const [next, id] = tool === 'state' ? addState(net, w.x, w.y) : addVerb(net, w.x, w.y)
      props.onCommit(next, { kind: tool, id })
      setTool(null)
      return
    }
    startPan(e)
  }

  const startDrag = (e: React.PointerEvent, ids: string[], snapEach: boolean) => {
    const origins = new Map<string, Pt>()
    for (const n of [...net.states, ...net.verbs]) if (ids.includes(n.id)) origins.set(n.id, { x: n.x, y: n.y })
    gesture.current = { kind: 'drag', start: toWorld(e.clientX, e.clientY), base: net, origins, snapEach, moved: false }
  }

  const onNodeDown = (e: React.PointerEvent, ref: NodeRef) => {
    if (e.button !== 0) return
    e.stopPropagation()
    if (space.current || mode === 'play') return startPan(e)
    if (props.touch && !isSel(ref.kind, ref.id)) return startPan(e, ref)
    onSelect(ref)
    startDrag(e, [ref.id], true)
  }

  const startRouteDrag = (e: React.PointerEvent, a: Arc, seg: number) => {
    gesture.current = { kind: 'route', ref: arcRef(a), seg, start: toWorld(e.clientX, e.clientY), base: net, routes, shapes, moved: false }
  }

  const anim = useFlightAnimation(play?.flight, net, routes)
  const marking = mode === 'play' && play ? (anim?.marking ?? play.marking) : undefined

  const selFocus = selection && (selection.kind === 'state' || selection.kind === 'verb') && !(props.touch && mode === 'play') ? selection : null
  const focus = hover ?? selFocus
  const neighbors = useMemo(() => {
    if (!focus) return undefined
    const s = new Set([focus.id])
    for (const a of net.arcs) if (a.state === focus.id || a.verb === focus.id) s.add(a.state).add(a.verb)
    return s.size > 1 ? s : undefined
  }, [focus?.id, net])

  const arcLayer = useMemo(() => {
    const touches = (a: Arc) => !!focus && (a.state === focus.id || a.verb === focus.id)
    const isSelected = (a: Arc) => selection?.kind === 'arc' && sameArc(a, selection)
    const rank = (a: Arc) => (isSelected(a) ? 2 : touches(a) ? 1 : 0)
    const byKey = new Map(net.arcs.map((a) => [arcKey(a), a]))
    const drawn = net.arcs.filter((a) => routes.has(arcKey(a)) && (shown(a.state) || shown(a.verb))).sort((a, b) => rank(a) - rank(b))
    const arcs = drawn.map((a) => {
      const pts = routes.get(arcKey(a))!
      const end = pts[pts.length - 1]
      const before = pts[pts.length - 2]
      const cls = ['arc', `arc-${a.kind}`, touches(a) && 'is-focus', focus && !touches(a) && 'is-faded', isSelected(a) && 'is-selected', a.via && 'is-placed']
        .filter(Boolean)
        .join(' ')
      const d = polylinePath(pts)
      return (
        <g key={arcKey(a)} className={cls} data-arc={arcKey(a)}>
          <path d={d} className="arc-line" />
          {a.kind === 'take' ? <path d={arrowAt(end, before)} className="arc-head" /> : null}
          {a.kind === 'give' ? <path d={arrowAt(pts[0], pts[1])} className="arc-head" /> : null}
          {a.kind === 'need' ? <ArcCap at={capAt(end, before, 3.5)} r={3.5} filled /> : null}
          {a.kind === 'unless' ? <ArcCap at={capAt(end, before, 4.5)} r={4.5} /> : null}
          {a.count !== 1 ? <CountBadge at={countBadgeAt(net, routes, a)} n={a.count} /> : null}
          {mode === 'edit'
            ? pts.slice(1).map((q, i) => {
                const p = pts[i]
                if (p.x === q.x && p.y === q.y) return null
                return (
                  <line
                    key={i}
                    x1={p.x}
                    y1={p.y}
                    x2={q.x}
                    y2={q.y}
                    className={`arc-hit ${p.y === q.y ? 'slide-y' : 'slide-x'}`}
                    onPointerDown={(e) => {
                      e.stopPropagation()
                      if (e.button !== 0 || space.current) return startPan(e)
                      if (props.touch && !isSelected(a)) return startPan(e, arcRef(a))
                      onSelect(arcRef(a))
                      startRouteDrag(e, a, i)
                    }}
                  >
                    <title>{`${a.kind} ${a.state} → ${a.verb}${a.via ? ' · placed by hand' : ''}. Drag to move its route.`}</title>
                  </line>
                )
              })
            : null}
          {mode === 'edit' && isSelected(a)
            ? pts.slice(1).map((q, i) => {
                const p = pts[i]
                return Math.abs(q.x - p.x) + Math.abs(q.y - p.y) < GRIP_MIN ? null : (
                  <rect key={`g${i}`} className="arc-grip" x={(p.x + q.x) / 2 - 3} y={(p.y + q.y) / 2 - 3} width={6} height={6} rx={1.5} />
                )
              })
            : null}
        </g>
      )
    })
    const dots = junctions.filter((j) => !onScreen || overlaps({ x0: j.at.x, y0: j.at.y, x1: j.at.x, y1: j.at.y }, onScreen.box)).map((j) => {
      const lit = j.arcs.some((k) => touches(byKey.get(k)!))
      return <circle key={`${j.arcs[0]}@${j.at.x},${j.at.y}`} className={`junction ${lit ? 'is-focus' : focus ? 'is-faded' : ''}`} cx={j.at.x} cy={j.at.y} r={2.6} />
    })
    return [...arcs, <g key="junctions">{dots}</g>]
  }, [net, routes, junctions, focus?.id, selection, mode, onScreen])

  const nodeCls = (id: string, extra: (string | false | undefined)[]) =>
    ['node', neighbors && !neighbors.has(id) && 'is-faded', ...extra].filter(Boolean).join(' ')
  const isSel = (kind: string, id: string) => selection?.kind === kind && 'id' in selection && selection.id === id
  const hoverProps = (ref: NodeRef) => ({
    onPointerEnter: () => setHover(ref),
    onPointerLeave: () => setHover((h) => (h?.id === ref.id ? null : h)),
  })

  const seatColor = (by: string) => (by === WORLD ? undefined : net.seats.find((s) => s.id === by)?.color)
  const viewer = play?.viewer

  const connectFrom = gesture.current.kind === 'connect' ? shapes.get(gesture.current.from.id) : undefined
  const ghost = mode === 'edit' && tool && cursor

  return (
    <div
      ref={wrap}
      className={`canvas mode-${mode} ${panning ? 'is-panning' : ''} ${tool ? 'is-placing' : ''}`}
      style={{ backgroundSize: `${20 * view.k}px ${20 * view.k}px`, backgroundPosition: `${view.x}px ${view.y}px` }}
    >
      <svg
        ref={svg}
        onPointerDown={onBackgroundDown}
        onPointerMove={(e) => setCursor(toWorld(e.clientX, e.clientY))}
        onPointerLeave={() => setCursor(null)}
        style={props.touch ? { touchAction: 'none' } : undefined}
      >
        <defs>
          <pattern id="fog" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" className="fog-bg" />
            <line x1="0" y1="0" x2="0" y2="6" className="fog-line" />
          </pattern>
        </defs>
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {hulls.filter((h) => !onScreen || overlaps(h.box, onScreen.box)).map(({ group, members, box }) => (
            <g
              key={group.id}
              className={`hull ${isSel('group', group.id) ? 'is-selected' : ''}`}
              onPointerDown={(e) => {
                if (mode !== 'edit' || space.current || e.button !== 0) return
                e.stopPropagation()
                if (props.touch && !isSel('group', group.id)) return startPan(e, { kind: 'group', id: group.id })
                onSelect({ kind: 'group', id: group.id })
                startDrag(e, members, false)
              }}
            >
              <rect x={box.x0} y={box.y0} width={box.x1 - box.x0} height={box.y1 - box.y0} rx={16} />
              <text x={box.x0 + 14} y={box.y0 + 18}>
                {group.label}
              </text>
            </g>
          ))}
          <g key={routes.size ? 'routed' : 'unrouted'} className={focus ? 'arcs has-focus' : 'arcs'}>
            {arcLayer}
          </g>
          {net.states.filter((p) => shown(p.id)).map((p) => {
            const ref: NodeRef = { kind: 'state', id: p.id }
            const n = marking ? (marking[p.id] ?? 0) : p.marks
            const hidden = mode === 'play' && !canSee(p, viewer)
            return (
              <g
                key={p.id}
                data-node={p.id}
                data-kind="state"
                className={nodeCls(p.id, ['state', isSel('state', p.id) && 'is-selected', p.ends !== undefined && n > 0 && mode === 'play' && 'is-reached'])}
                transform={`translate(${p.x},${p.y})`}
                onPointerDown={(e) => onNodeDown(e, ref)}
                {...hoverProps(ref)}
              >
                {p.ends !== undefined ? <circle r={STATE_R + 4} className="outcome-ring" /> : null}
                <circle r={p.r ?? STATE_R} className="state-body" fill={hidden ? 'url(#fog)' : undefined} />
                {p.lines ? (
                  <text className="fields" y={(-(p.lines.length - 1) * FIELD_LINE) / 2 + 3}>
                    {p.lines.map((l, i) => (
                      <tspan key={i} x={0} dy={i ? FIELD_LINE : 0}>
                        {l}
                      </tspan>
                    ))}
                  </text>
                ) : hidden ? <text className="fog-q" dy={5}>?</text> : <Marks n={n} />}
                {p.seenBy !== 'all' ? <PrivateBadge seenBy={p.seenBy} net={net} /> : null}
                <text className="label" y={(p.r ?? STATE_R) + 11}>
                  {p.label}
                </text>
                <title>{`${p.id}${p.ends !== undefined ? ` · ends "${p.ends}"` : ''}`}</title>
              </g>
            )
          })}
          {net.verbs.filter((v) => shown(v.id)).map((v) => {
            const ref: NodeRef = { kind: 'verb', id: v.id }
            const chance = chanceVerbs.has(v.id)
            const w = verbWidth(v, chance)
            const dw = dieWidth(v, chance)
            const color = seatColor(v.by)
            const legal = play?.legal.has(v.id)
            const waiting = !legal && play?.waiting.has(v.id)
            const playState = mode !== 'play' ? undefined : legal ? 'is-legal' : waiting ? 'is-waiting' : 'is-idle'
            return (
              <g
                key={v.id}
                data-node={v.id}
                data-kind="verb"
                className={nodeCls(v.id, ['verb', v.by === WORLD && 'is-world', isSel('verb', v.id) && 'is-selected', playState])}
                transform={`translate(${v.x},${v.y})`}
                style={{ ['--seat' as string]: color ?? 'var(--world)' }}
                onPointerDown={(e) => onNodeDown(e, ref)}
                onClick={() => legal && play?.onSpeak(v.id)}
                {...hoverProps(ref)}
              >
                {legal ? <rect className="glow" x={-w / 2 - 4} y={-VERB_H / 2 - 4} width={w + 8} height={VERB_H + 8} rx={10} /> : null}
                <rect className="verb-body" x={-w / 2} y={-VERB_H / 2} width={w} height={VERB_H} rx={6} />
                <text className="verb-label" x={dw / 2} dy={4} fill={color ? readableOn(color) : undefined}>
                  {v.label}
                </text>
                {v.priority !== 0 ? (
                  <g className="badge" transform={`translate(${priorityBadge(w).x},${priorityBadge(w).y})`}>
                    <circle r={PRIORITY_R} />
                    <text dy={3.5}>{v.priority}</text>
                    <title>{`priority ${v.priority}`}</title>
                  </g>
                ) : null}
                {chance ? <Die x={-w / 2 + 11} weight={v.weight} fill={color ? readableOn(color) : '#ffffff'} /> : null}
                <title>{`${v.id} · ${v.by === WORLD ? 'world' : `by ${v.by}`}`}</title>
              </g>
            )
          })}
          {anim?.tokens.map((t, i) => <circle key={i} className="token" cx={t.x} cy={t.y} r={4} />)}
          {connectFrom && connectTo ? <line className="connect-preview" x1={connectFrom.x} y1={connectFrom.y} x2={connectTo.x} y2={connectTo.y} /> : null}
          {ghost ? (
            tool === 'state' ? (
              <circle className="ghost" cx={snap(ghost.x)} cy={snap(ghost.y)} r={STATE_R} />
            ) : (
              <rect className="ghost" x={snap(ghost.x) - 40} y={snap(ghost.y) - VERB_H / 2} width={80} height={VERB_H} rx={6} />
            )
          ) : null}
        </g>
      </svg>
      <div className="zoom">
        <button onClick={() => setView((v) => zoomAtCenter(v, 1 / 1.25, svg.current!))} aria-label="Zoom out">
          −
        </button>
        <span>{Math.round(view.k * 100)}%</span>
        <button onClick={() => setView((v) => zoomAtCenter(v, 1.25, svg.current!))} aria-label="Zoom in">
          +
        </button>
        <button onClick={fit}>Fit</button>
      </div>
    </div>
  )
}

const zoomAtCenter = (v: View, f: number, el: SVGSVGElement): View => {
  const r = el.getBoundingClientRect()
  const k = Math.min(4, Math.max(0.15, v.k * f))
  const cx = r.width / 2
  const cy = r.height / 2
  return { k, x: cx - (cx - v.x) * (k / v.k), y: cy - (cy - v.y) * (k / v.k) }
}

function Marks({ n }: { n: number }) {
  if (n <= 0) return null
  if (n > 5)
    return (
      <text className="marks-n" dy={5}>
        {n}
      </text>
    )
  return (
    <>
      {DOTS[n].map((d, i) => (
        <circle key={i} className="mark" cx={d.x} cy={d.y} r={3} />
      ))}
    </>
  )
}

function PrivateBadge({ seenBy, net }: { seenBy: SeatId[]; net: Net }) {
  const names = seenBy.map((s) => net.seats.find((x) => x.id === s)?.name ?? s)
  const text = names.length ? names.join(', ') : 'nobody'
  const w = 22 + text.length * 5.6
  return (
    <g className="private" transform={`translate(${STATE_R - 6},${-STATE_R - 6})`}>
      <rect x={0} y={-8} width={w} height={16} rx={8} />
      <g transform="translate(9,0)">
        <path d="M-5,0 Q0,-5 5,0 Q0,5 -5,0 Z" className="eye" />
        <line x1={-4.5} y1={4} x2={4.5} y2={-4} className="eye-slash" />
      </g>
      <text x={18} y={3.5}>
        {text}
      </text>
      <title>{`Private: seen by ${text}`}</title>
    </g>
  )
}

function Die({ x, weight, fill }: { x: number; weight: number; fill: string }) {
  return (
    <g className="die" transform={`translate(${x},0)`} style={{ color: fill }}>
      <rect x={-5.5} y={-5.5} width={11} height={11} rx={2.5} />
      <circle cx={-2.2} cy={-2.2} r={1.1} />
      <circle cx={2.2} cy={2.2} r={1.1} />
      {weight !== 1 ? (
        <text x={9} y={3.5}>
          ×{weight}
        </text>
      ) : null}
      <title>{`Chance: weight ${weight} among world verbs at the same priority`}</title>
    </g>
  )
}

function CountBadge({ at, n }: { at: Pt; n: number }) {
  return (
    <g className="arc-count" transform={`translate(${at.x},${at.y})`}>
      <rect x={-8} y={-7} width={16} height={14} rx={7} />
      <text dy={4}>{n}</text>
    </g>
  )
}

function ArcCap({ at, r, filled }: { at: Pt; r: number; filled?: boolean }): ReactNode {
  return <circle cx={at.x} cy={at.y} r={r} className={filled ? 'arc-cap is-filled' : 'arc-cap'} />
}

export function Legend() {
  const item = (label: string, line: ReactNode) => (
    <li>
      <svg width="40" height="14" viewBox="0 0 40 14">
        {line}
      </svg>
      {label}
    </li>
  )
  return (
    <details className="legend">
      <summary>Legend</summary>
      <ul>
        {item('take', <><line x1="2" y1="7" x2="32" y2="7" className="lg-line" /><path d="M38,7 L30,3 L30,11 Z" className="lg-head" /></>)}
        {item('give', <><line x1="2" y1="7" x2="32" y2="7" className="lg-line" /><path d="M38,7 L30,3 L30,11 Z" className="lg-head" /></>)}
        {item('need (test)', <><line x1="2" y1="7" x2="32" y2="7" className="lg-line lg-dash" /><circle cx="35" cy="7" r="3" className="lg-head" /></>)}
        {item('unless (inhibitor)', <><line x1="2" y1="7" x2="31" y2="7" className="lg-line" /><circle cx="35" cy="7" r="4" className="lg-open" /></>)}
      </ul>
    </details>
  )
}

function useFlightAnimation(flight: Flight | undefined, net: Net, routes: Map<ArcKey, Pt[]>) {
  const [state, setState] = useState<{ tokens: Pt[]; marking: Marking } | null>(null)
  const paths = useRef(routes)
  paths.current = routes
  useEffect(() => {
    if (!flight || !flight.frames.length || reducedMotion()) return setState(null)
    const byVerb = new Map<string, Arc[]>()
    for (const a of net.arcs) byVerb.set(a.verb, [...(byVerb.get(a.verb) ?? []), a])
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      // A frame's timestamp can predate t0, which was read after the frame began.
      const t = Math.max(0, now - t0)
      const i = Math.floor(t / FRAME_MS)
      if (i >= flight.frames.length) return setState(null)
      const f = (t % FRAME_MS) / FRAME_MS
      const { verb, before } = flight.frames[i]
      const arcs = byVerb.get(verb) ?? []
      const mid = { ...before }
      for (const a of arcs) if (a.kind === 'take') mid[a.state] -= a.count
      const moving = arcs.filter((a) => (f < 0.5 ? a.kind === 'take' : a.kind === 'give'))
      const u = ease(f < 0.5 ? f * 2 : (f - 0.5) * 2)
      const tokens = moving.flatMap((a) => {
        const pts = paths.current.get(arcKey(a))
        return pts ? [pointAlong(pts, a.kind === 'give' ? 1 - u : u)] : []
      })
      setState({ tokens, marking: mid })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [flight?.key])
  return state
}

const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)
