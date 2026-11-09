import { useEffect, useMemo, useRef, useState } from 'react'
import type { Net } from './model'
import { chanceTies, shapesOf, type Pt, type Shape } from './geometry'
import { arcKey, priorFor, routeArcs, type ArcKey, type Prior } from './route'

interface Settled {
  net: Net
  shapes: Map<string, Shape>
  routes: Map<ArcKey, Pt[]>
}

const SETTLE_MS = 120

/**
 * Routes for the net on screen. A full route (two passes over every cable) runs in a worker once the net has been
 * still for a moment, or at once on first load; until it lands, the canvas routes only what changed since the last
 * full route, on the main thread, keeping every other cable where it was. That is what keeps a node drag smooth.
 * Before the first full route, or after a change that leaves nothing to keep, no arcs are drawn.
 */
export function useRoutes(net: Net, shapes: Map<string, Shape>): Map<ArcKey, Pt[]> {
  const [settled, setSettled] = useState<Settled | null>(null)
  const worker = useRef<Worker | null>(null)
  const asked = useRef<{ id: number; net: Net } | null>(null)

  useEffect(() => {
    const w = new Worker(new URL('./route.worker.ts', import.meta.url), { type: 'module' })
    w.onmessage = (e: MessageEvent<{ id: number; routes: [ArcKey, Pt[]][] }>) => {
      const req = asked.current
      if (!req || req.id !== e.data.id) return
      setSettled({ net: req.net, shapes: shapesOf(req.net, chanceTies(req.net)), routes: new Map(e.data.routes) })
    }
    worker.current = w
    return () => w.terminate()
  }, [])

  useEffect(() => {
    if (settled?.net === net) return
    const t = setTimeout(
      () => {
        asked.current = { id: (asked.current?.id ?? 0) + 1, net }
        worker.current?.postMessage(asked.current)
      },
      settled ? SETTLE_MS : 0,
    )
    return () => clearTimeout(t)
  }, [net, settled])

  return useMemo(() => {
    if (settled?.net === net) return settled.routes
    const prior = settled && priorFor(settled, net, shapes)
    return prior && keepsSome(prior, net) ? routeArcs(net, shapes, prior) : NONE
  }, [net, shapes, settled])
}

const NONE = new Map<ArcKey, Pt[]>()

/** With nothing to keep, a route here would be a full one on the main thread, so the canvas waits for the worker. */
const keepsSome = (prior: Prior, net: Net) => net.arcs.some((a) => prior.routes.has(arcKey(a)) && !prior.moved.has(a.state) && !prior.moved.has(a.verb))
