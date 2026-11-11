# RUNS Network viewer

Draws the RUNS text of `runs/` as its Petri net: each Record a place with its fields written inside, each Processor a transition, a line ending in a dot for each Record a Processor reads and an arrow for each it writes. When the Records have kinds, they sit in three columns (game, interface, presentation: the Rules region, the boundary Records, the Realization region), and a Processor that touches both a game Record and a presentation Record is red.

`tools/runs_net.py` reads the RUNS text through the evaluator's loader and writes the data the viewer draws. Nothing in the drawing is written by hand.

```sh
npm install
npm run net        # runs/ to public/spacewar.json
npm run dev        # serves on port 5173 on every interface
```

`?net=other.json` draws another file from `public/`.

On a phone (narrower than 720 pixels, or a short touch screen) the drawing is the same, with touch gestures, and the details sit in a sheet that slides up from the bottom. A name in the details selects that Record or Processor and brings it into view.

The canvas, the arc router and the geometry in `src/canvas/` are copied from the MAPS studio (`maps-notation/studio/src`, commit 667d764) and cut down to a viewer: no editing tools, no chance, places sized to hold their fields. The drawing is a RUNS Network, not a MAPS design.
