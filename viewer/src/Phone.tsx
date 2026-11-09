import { useEffect, useRef, useState, type ReactNode } from 'react'

export const PHONE_QUERY = '(max-width: 720px), (max-height: 500px) and (pointer: coarse)'
/** Keep in step with the landscape block in canvas/styles.css, where the sheet docks as a column. */
const DOCKED_QUERY = '(orientation: landscape) and (max-height: 500px)'

export function useMediaQuery(query: string) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setMatch(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [query])
  return match
}

type Snap = 'peek' | 'half' | 'full'
const ORDER: Snap[] = ['peek', 'half', 'full']

interface Props {
  title: string
  counts: string
  canvas: ReactNode
  /** What the sheet shows when it peeks: the selection's kind and name. */
  eyebrow: string
  heading: string
  /** Changes whenever something is selected, so the sheet opens to show it. */
  reveal: string | null
  children: ReactNode
}

/** The phone layout: the Network fills the screen, and a sheet from the
 * bottom holds what the side panel holds on a wide screen. */
export function PhoneLayout(props: Props) {
  const [snap, setSnap] = useState<Snap>('peek')
  const [dragH, setDragH] = useState<number | null>(null)
  const docked = useMediaQuery(DOCKED_QUERY)
  const sheet = useRef<HTMLElement>(null)
  const drag = useRef<{ y: number; h: number; moved: boolean } | null>(null)

  useEffect(() => {
    if (props.reveal) setSnap((s) => (s === 'peek' ? 'half' : s))
  }, [props.reveal])

  const onGripDown = (e: React.PointerEvent) => {
    drag.current = { y: e.clientY, h: sheet.current!.getBoundingClientRect().height, moved: false }
    ;(e.target as Element).setPointerCapture(e.pointerId)
  }
  const onGripMove = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d) return
    const dy = e.clientY - d.y
    if (Math.abs(dy) > 6) d.moved = true
    if (d.moved) setDragH(Math.max(56, d.h - dy))
  }
  const onGripUp = (e: React.PointerEvent) => {
    const d = drag.current
    drag.current = null
    setDragH(null)
    if (!d) return
    if (!d.moved) return setSnap(snap === 'peek' ? 'half' : 'peek')
    const dy = e.clientY - d.y
    const steps = Math.round(Math.abs(dy) / (window.innerHeight * 0.25)) || 1
    const i = ORDER.indexOf(snap)
    setSnap(ORDER[Math.max(0, Math.min(2, i + (dy < 0 ? steps : -steps)))])
  }

  return (
    <div className="phone-app">
      <header className="phone-top">
        <span className="phone-title" title={props.title}>
          {props.title}
        </span>
        <span className="phone-counts">{props.counts}</span>
      </header>
      <main className="phone-stage">{props.canvas}</main>
      <section
        ref={sheet}
        className={`sheet snap-${snap} ${dragH !== null ? 'is-dragging' : ''}`}
        style={dragH !== null ? { height: dragH } : undefined}
        aria-label="Details"
      >
        <div
          className="sheet-grip"
          role="button"
          aria-label={snap === 'peek' ? 'Expand details' : 'Collapse details'}
          onPointerDown={onGripDown}
          onPointerMove={onGripMove}
          onPointerUp={onGripUp}
          onPointerCancel={() => ((drag.current = null), setDragH(null))}
        >
          <span />
        </div>
        <button className="sheet-summary" onClick={() => setSnap(docked || snap !== 'peek' ? snap : 'half')}>
          <span className="eyebrow">{props.eyebrow}</span>
          <span className="sheet-summary-title">{props.heading}</span>
          <span className="chev" aria-hidden>
            ›
          </span>
        </button>
        <div className="sheet-body">{props.children}</div>
      </section>
    </div>
  )
}
