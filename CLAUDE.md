# Standing orders: the Spacewar conversion

This repo converts Spacewar! 3.1 into **pure** RUNS. The conversion is a reorganization of the existing program (the PDP-1 assembly, and the C lift that builds the same image), never a port and never a rewrite of behavior. The RUNS text, compiled with the PDP-1 binding, builds the original image at every commit.

## Pure

- A **Record** holds data and nothing else: named fields with values. A Record that holds instructions the game runs (`insn`, `jump`) holds logic and is impure.
- A **Processor** holds no state. It takes values from the Records it declares and gives values to the Records it declares.
- Every Record is a `game`, `interface`, or `presentation` Record. A Processor touches game and interface Records, or presentation and interface Records. Removing every presentation Processor leaves the game's Records the same at every step.
- The **Network** is one net: the game's Petri net, Records as places and Processors as transitions. Its form in the text is not settled yet (`todo.md`, Round 12); until it is, write order the way the current network blocks do.

`INTENT.md` holds the model and the reasons; read its first two sections before you design anything.

## Every commit

1. `uv run -q python tools/runsc.py | tail -1` prints `MATCH` with sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
2. `tools/check_all.sh` passes. It takes about 6 minutes; run it in the background and edit nothing under `runs/`, `pdp1/` or `tools/` while it runs.
3. The purity report gains no line: `PYTHONPATH=tools uv run -q python tools/check_purity.py --against HEAD` exits 0. It allows a new line only where a Record just got its kind and revealed an impurity already there; the decisions row lists those.
4. A row in `docs/decisions.tsv` for each decision: what, why, evidence, result.

## Where a change goes

Change the lowest layer that works, in this order:

1. **The RUNS text.** Most of the work lives here. Sketch at least two pure shapes of the routine and compile each before you reach for layer 2 or 3.
2. **The binding** (`pdp1/*.toml`). Per-game layout facts only, in the binding's existing vocabulary.
3. **The compiler** (`tools/runsc.py`). It becomes the one PDP-1 back end for every PDP-1 game, so it changes rarely. A change is a rule a second PDP-1 program would use, and its decisions row names the idiom and why it is general.

The binding holds layout, never logic: no expression, statement, or number the game computes with (`pdp1/README.md`).

Purity is fixed. When a pure shape will not compile to the original image, the compiler or binding grows; the shape stays pure.

## Converting one interaction

1. Read the original for it: `source/spacewar3.1_complete.txt`, the lift in `lift/`, and the current RUNS.
2. Name its data as Records, each with a kind, and its rules as Processors, each pure.
3. Wire them into the Network in the original's order.
4. Compile. On `MATCH`, run the checks of every commit. Otherwise try the next shape, then the binding, then the compiler, in the order above.
5. Done when the interaction is pure, the image matches, `check_all.sh` passes, and the purity count fell.

## Evidence

- The game alone: `PYTHONPATH=tools uv run -q python tools/check_frame.py 300 alone` removes every presentation routine and Record and compares what is left with the whole program, frame by frame. A Record that differs is game work still living in a presentation Processor.
- Verify on the real artifact: the image, SIMH, the evaluator. A new check earns its place when a planted defect turns it red with the disagreement you predicted.
- The purity report is the progress meter. Every impurity stays on it until it is converted; a flag, marker, or exception that hides one from the report is the shortcut this project exists to refuse.
- A drawing or report is a transcription of the text: it shows what the files state, in the files' own structure.

## Where things are

- `todo.md`, the last round: the plan, the riskiest part, and where the work stands. Read it before the first change of a session.
- `pdp1/README.md`: the binding's vocabulary and the rules `runsc` enforces. Read it before you change the binding or the compiler.
- `../runs-spec`: the RUNS spec. `NETWORK_TOPOLOGY.md` (Records, kinds, Networks) and `CONVERSION_PROCESS.md` (how a conversion goes) bear on every unit. A language change lands there too, with examples that `../runs-spec/tools/check_examples.py ../runs-spec .` runs.
- `viewer/`: draws the RUNS text (`npm run net`, then `npm run dev`).
