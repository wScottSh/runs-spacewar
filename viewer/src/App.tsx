import { useEffect, useMemo, useState } from 'react'
import { Canvas } from './canvas/Canvas'
import type { Selection } from './canvas/edit'
import type { Net } from './canvas/model'
import { countLabel, fieldLine, processorId, recordId, toCanvas, type RunsNet } from './layout'
import { PHONE_QUERY, PhoneLayout, useMediaQuery } from './Phone'

const SOURCE = new URLSearchParams(location.search).get('net') ?? 'spacewar.json'

/** Moving nodes and arcs is allowed; the RUNS text decides what exists. */
const sameStructure = (a: Net, b: Net) =>
  a.states.length === b.states.length &&
  a.verbs.length === b.verbs.length &&
  a.arcs.length === b.arcs.length &&
  a.states.every((s, i) => s.id === b.states[i].id) &&
  a.verbs.every((v, i) => v.id === b.verbs[i].id)

export function App() {
  const [runs, setRuns] = useState<RunsNet | null>(null)
  const [net, setNet] = useState<Net | null>(null)
  const [selection, setSelection] = useState<Selection>(null)
  const [error, setError] = useState<string | null>(null)
  const [fitKey, setFitKey] = useState(0)
  const phone = useMediaQuery(PHONE_QUERY)
  const loaded = net !== null
  useEffect(() => {
    if (loaded) requestAnimationFrame(() => setFitKey((k) => k + 1))
  }, [loaded, phone])

  useEffect(() => {
    fetch(SOURCE)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${SOURCE}: ${r.status}`))))
      .then((data: RunsNet) => setRuns(data))
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (runs) setNet(toCanvas(runs, phone))
  }, [runs, phone])

  const keep = (next: Net) => setNet((now) => (now && sameStructure(now, next) ? next : now))

  if (error) return <p style={{ padding: 20 }}>Could not load {error}. Run <code>npm run net</code> first.</p>
  if (!runs || !net) return null
  const counts = `${runs.records.length} Records, ${runs.processors.length} Processors`
  const canvas = (
    <Canvas
      net={net}
      mode="edit"
      selection={selection}
      onSelect={setSelection}
      onCommit={keep}
      onCheckpoint={() => {}}
      onLive={keep}
      play={undefined}
      fitKey={fitKey}
      touch={phone}
    />
  )
  if (phone) {
    const id = selection && 'id' in selection ? selection.id : null
    const [kind, name] = id ? id.split(':') : ['RUNS Network', runs.title]
    return (
      <PhoneLayout title={runs.title} counts={counts} canvas={canvas} eyebrow={kind} heading={name} reveal={id}>
        <Side runs={runs} selection={selection} onSelect={setSelection} />
      </PhoneLayout>
    )
  }
  return (
    <div className="runs-app">
      <header className="topbar">
        <strong>RUNS Network</strong>
        <span>{runs.title}</span>
        <span className="muted">{counts}</span>
      </header>
      <main className="stage">{canvas}</main>
      <Side runs={runs} selection={selection} onSelect={setSelection} />
    </div>
  )
}

function Side({ runs, selection, onSelect }: { runs: RunsNet; selection: Selection; onSelect: (s: Selection) => void }) {
  const toRecord = (name: string) => (
    <li key={name}>
      <button className="runs-link" onClick={() => onSelect({ kind: 'state', id: recordId(name) })}>
        {name}
      </button>
    </li>
  )
  const toProcessor = (name: string) => (
    <li key={name}>
      <button className="runs-link" onClick={() => onSelect({ kind: 'verb', id: processorId(name) })}>
        {name}
      </button>
    </li>
  )
  const byId = useMemo(
    () => ({
      records: new Map(runs.records.map((r) => [recordId(r.name), r])),
      processors: new Map(runs.processors.map((p) => [processorId(p.name), p])),
    }),
    [runs],
  )
  const id = selection && 'id' in selection ? selection.id : null
  const record = id ? byId.records.get(id) : undefined
  const processor = id ? byId.processors.get(id) : undefined
  const typed = runs.records.some((r) => r.kind)

  if (record) {
    const users = runs.processors.filter((p) => p.reads.includes(record.name) || p.writes.includes(record.name))
    return (
      <aside className="runs-side">
        <h2>
          {record.stream ? 'stream' : 'record'} {record.name}
          {countLabel(record.count)}
        </h2>
        <p className="kind">{record.kind ? `${record.kind} record` : 'no kind yet'}</p>
        <strong>Fields</strong>
        <ul>
          {record.fields.map((f) => (
            <li key={f.name}>
              <code>{fieldLine(f)}</code>
            </li>
          ))}
        </ul>
        <strong>Written by</strong>
        <ul>{users.filter((p) => p.writes.includes(record.name)).map((p) => toProcessor(p.name))}</ul>
        <strong>Read by</strong>
        <ul>{users.filter((p) => !p.writes.includes(record.name)).map((p) => toProcessor(p.name))}</ul>
      </aside>
    )
  }
  if (processor) {
    return (
      <aside className="runs-side">
        <h2>processor {processor.name}</h2>
        <p className="kind">
          {processor.mixed ? 'touches game and presentation Records' : processor.side ? `the ${processor.side}'s` : 'no side yet'}
          {processor.file ? ` · ${processor.file}.runs-prim` : ''}
        </p>
        <strong>Reads</strong>
        <ul>{processor.reads.map(toRecord)}</ul>
        <strong>Writes</strong>
        <ul>{processor.writes.map(toRecord)}</ul>
      </aside>
    )
  }
  return (
    <aside className="runs-side">
      <h2>How to read it</h2>
      <p>Each circle is a Record, with its fields written inside. Each box is a Processor. A line ending in a dot is a Record the Processor reads; an arrow is a Record it writes.</p>
      <p>
        {typed
          ? 'Records sit in three columns by kind: game, interface, presentation. A red box touches both a game Record and a presentation Record.'
          : 'The Records have no kinds yet, so Processors are grouped by the file they are written in, and Records that several files touch sit in the middle.'}
      </p>
      <ul className="runs-key">
        <li>
          <span className="swatch" style={{ background: '#2e6f9e' }} /> the game's Processor
        </li>
        <li>
          <span className="swatch" style={{ background: '#b8662a' }} /> the presentation's Processor
        </li>
        <li>
          <span className="swatch" style={{ background: '#c0392b' }} /> touches game and presentation
        </li>
        <li>
          <span className="swatch" style={{ background: '#8a9099' }} /> no side yet
        </li>
      </ul>
      <p>Hover a node to light its lines. Click one to see its fields or contract. Drag to rearrange; the RUNS text decides what exists.</p>
    </aside>
  )
}
