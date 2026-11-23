# Standing orders: the Spacewar conversion

This repo converts Spacewar! 3.1 into **pure** RUNS. The conversion reorganizes the existing program (the PDP-1 assembly, and the C lift that builds the same image); it is never a re-vibe and never a rewrite of behavior. The RUNS source, compiled with the PDP-1 Declarations, builds the original image at every commit.

What the conversion is for: the reference for the game, not a Game Port or a Variant; the binary as the Original and the only oracle that proves every input, with the RUNS source carrying everything the program does, and code the program never contained left to the machine; a process meant to repeat for every game; and stateless, named Bundles that other games can take.

Before you design anything, read `../.github/GLOSSARY.md` (Conversion), `../runs-spec/README.md` (What the work is for), and the first two sections of `INTENT.md` (the model and the reasons). `../.github/GLOSSARY.md` is the EGS vocabulary and governs where a doc here disagrees, unless the user has said otherwise more recently: then the user's newer word governs both, and GLOSSARY.md gets fixed. A question the user hasn't decided stays open, even where GLOSSARY.md reads as settled (`todo.md`, Open with the user).

Open with the user, and built only after the user decides:

1. **The order of the process.** The user wants each deep module of the C lift to become one large Processor that gives the tick's shape, then be refactored down into game-logic groupings. The bottom-up, routine-by-routine path taken so far was the wrong order; a better, automatable process is undecided.
2. **Granularity.** The shape of the Bundles (smallest piece, naming, sharing across games) is undecided. Split no further and start no package work until the user decides. A Bundle whose inputs are one game's Records can't be shared: a known problem, not a pattern to copy.

## Pure

- A **Record** holds data and nothing else: named Fields with values. A Record that holds instructions the game runs (`insn`, `jump`) holds logic and is impure.
- Only a Processor changes a Record (`../.github/GLOSSARY.md`, Record): it takes the value out, computes, and may put the result back in the same place. The wires and Guards order any two Processors that touch one place. A changed value goes back in its own Record; a new Record is never needed just because a value changed (user, 2026-11-14).
- A **Processor** holds no state and names no Records. It is one file (`.runs-prim`) that takes values on its inputs (`in`, `inout`) and gives values on its outputs (`out`, `inout`); the Network wires a Record Field to each (`../.github/GLOSSARY.md`, Network).
- Every Record has a **kind**: `game` (the Game Logic), `interface` (a Interface Record) or `presentation` (the Presentation). A Processor touches game and Interface Records, or Presentation and Interface Records. Removing every Presentation Processor leaves the game's Records the same at every step. The split is the enduring-games pattern, a convention and not a RUNS primitive (`../.github/GLOSSARY.md`, Processor); this project enforces it as its own rule.
- The **Network** is one net: the game's colored Petri net, written as Network files (`runs/**/*.net`) of places, transitions and arcs. Records are places, Processors are transitions.
  - The order lives in the Network and nowhere else: the arcs and their Guards write down which Processor fires after which, the order the original's steps ran in.
  - Firing is parallel wherever no arc orders two Processors; where two could race on one place, a wire or a Guard makes one wait for the other.
  - A Guard is part of an arc and tests only values Records hold; a Processor computes any value it needs into a Record first. The Guards on one place form a complete partition, exactly one true, with `when else` for an open-typed value (`../.github/GLOSSARY.md`, Guard).
  - A Network may pass which slot to a transition (`name: routine(slot)`).

## Every commit

Checks 1-4 catch a change that breaks the image or the game, so run them when the commit changes something they read. `uv run -q python tools/gate_inputs.py` lists those changes: the RUNS source, the Declarations, the sources, the oracle, and the tools `check_all.sh` reaches. Empty output (Markdown, `docs/`, a report script nothing runs) means no check runs, and `check_all.sh` skips itself. A rule here that does nothing for its purpose in the case at hand is a defect to raise, not to follow. Every commit gets steps 5 and 6.

1. `uv run -q python tools/runsc.py | tail -1` prints `identical to the original` with sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
2. `tools/check_all.sh` passes. It prints each step's time and its own total. Run it in the background, and leave `runs/`, `pdp1/` and `tools/` unedited while it runs.
3. The purity report stays at 0: `PYTHONPATH=tools uv run -q python tools/check_purity.py --against HEAD` exits 0.
4. The PDP-1 Declarations do not grow: `uv run -q python tools/check_declarations.py` exits 0 (The PDP-1 Declarations, below).
5. A row in `docs/decisions.tsv` for each decision: what, why, evidence, result.
6. Push each verified commit to main: `git push origin HEAD:main`, fast-forward only (rebase on `origin/main` first if it moved). Standing order from the user; no need to ask. The same holds for every EGS repo this work touches (`../runs-spec`, `../.github` and the org's other repos): push each verified commit to its main without asking (user, 2026-11-11: "it's a general rule").

## Where a change goes

1. **The RUNS source.** The work lives here. Source that is hard to write means its shape is wrong: sketch at least two pure shapes and compile each.
2. **The compiler** (`tools/runsc.py`) is one general PDP-1 compiler for every PDP-1 program. It holds machine detail (registers, addresses, scratch words, the instructions that move a word) and no Game Logic: no limit or order that changes what happens in the game (`../runs-spec/CONVERSION_PROCESS.md`, Game Logic or machine). A change is a general PDP-1 rule that a second PDP-1 program uses, never a fix to make one game's shape compile; its decisions row names the idiom and that program. The user: "there should be no changes at all to the compiler... Everything should be in how the network is structured" (2026-11-11, meaning no bending it for one game), "the compiler being a general pdp1 compiler" (2026-11-11), and "that's the job for the compiler to make sure that it runs on the PDP-1" (2026-11-14).
3. **Neither works.** Purity is fixed: the shape stays pure, and the work stops for a report of the shapes tried and the evidence.

### The PDP-1 Declarations

`pdp1/*.toml` is the half of the PDP-1 platform code that never runs: the 1962 programmer's arbitrary choices about where the game's data lives and how routines are called, nothing the game computes. A Game Port leaves them behind with the PDP-1 Presentation. Because they never run, they may name game Records, which a Presentation Processor may not. They are no place to solve what is hard to write in the source. `tools/check_declarations.py` counts entries, not lines (every scalar value and every list element of the TOML), and fails any commit that adds one, a name added to an existing list included. Only the user raises the count in `pdp1/DECLARATIONS`, and the decisions row quotes the user. A commit that removes entries lowers it. The code still says `Bindings` and `BindError`; read them as the Declarations. The vocabulary and the rules `runsc` enforces are in `pdp1/README.md`.

## Converting one interaction

1. Read the original for it: `source/spacewar3.1_complete.txt`, the lift in `lift/`, and the current RUNS.
2. Sort every detail with one question, asked of the Game Logic (what the program does, given the PDP-1's deterministic behavior) and never of intent: does changing it change anything that happens in the game? `../runs-spec/CONVERSION_PROCESS.md`, Game Logic or machine: the one test.
   - Yes: Game Logic, stated in the RUNS source. The arithmetic, limits, the order of two steps where swapping them changes a result, PDP-1 behavior the program reaches (a read past an array whose value play observes).
   - No: the machine, left to the Declarations or the compiler. Registers, addresses, scratch words, order that changes nothing.
   - Follow the data across the PDP-1's edge: device reads and core the program never set are inputs; a value that only flows out to the scope is Presentation.
   - Glitches emerge from the complete Game Logic. They are no category of their own, and the conversion neither recreates nor removes one.
   - Leaving out a behavior the program has changes the Game Logic, which makes a Variant. Code the program never contained is the machine's, and the conversion does not carry it.
3. Name the Game Logic's data as Records, each with a Kind, and its steps as Processors, each pure. Wire them into the Network in the order the original's steps run, one pull-change-put-back per step: a Processor takes a value from a Record, changes it, and puts it back; the next Processor takes it from there. Use the Records the Original had and add no interim one. Nothing computes between ticks: whatever the PDP-1 computed between two steps is a step in the Network.
4. Compile. When the image is identical to the Original, run the checks of every commit. Otherwise try the next shape, then a general compiler rule (Where a change goes).
5. Done when the interaction is pure, the image matches, `check_all.sh` passes, and the purity report stays at 0.

## Evidence

- The game alone: `PYTHONPATH=tools uv run -q python tools/check_frame.py 300 alone` removes every Presentation routine and Record and compares what is left with the whole program, frame by frame. A Record that differs is game work still living in a Presentation Processor.
- Verify on the real artifact: the image, SIMH, the evaluator. A new check earns its place when a planted defect turns it red with the disagreement you predicted.
- The purity report is the progress meter. Every impurity stays on it until it is converted; a flag, marker, or exception that hides one from the report is the shortcut this project exists to refuse.
- A drawing or report is a transcription of the source: it shows what the files state, in the files' own structure.

## Where things are

- `todo.md`: the last round's plan, its riskiest part, and where the work stands. Read it before the session's first change.
- `pdp1/README.md`: the Declarations' vocabulary and the rules `runsc` enforces. Read it before you change the Declarations or the compiler.
- `../runs-spec`: the RUNS spec. `NETWORK_TOPOLOGY.md` (Records, kinds, Networks) and `CONVERSION_PROCESS.md` (how a conversion goes) bear on every unit. A language change lands there too, with examples that `../runs-spec/tools/check_examples.py ../runs-spec .` runs.
- `viewer/`: draws the RUNS source (`npm run net`, then `npm run dev`).

## Agent skills

### Issue tracker

GitHub issues on `wScottSh/runs-spacewar`, via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the root. See `docs/agents/domain.md`.
