# Standing orders: the Spacewar conversion

This repo converts Spacewar! 3.1 into **pure** RUNS. The conversion is a reorganization of the existing program (the PDP-1 assembly, and the C lift that builds the same image), never a re-vibe and never a rewrite of behavior. The RUNS source, compiled with the PDP-1 declarations, builds the original image at every commit.

What the conversion is for: the reference for the game, not a Port or a Variant; the binary as the only oracle that proves every input; a process meant to repeat for every game; and stateless, named bundles that other games can take. `../.github/CONTEXT.md` (Conversion) and `../runs-spec/README.md` § What the work is for state it. Read both before you design anything.

Open with the user, not to be built ahead of a decision: (1) the order of the process. The user wants each deep module of the C lift to become one large Processor that gives the tick's shape, then refactored down into game-logic groupings; the bottom-up, routine-by-routine path taken so far was the wrong order, and a better, automatable process is undecided. (2) Granularity: the shape of the bundles (smallest piece, naming, sharing across games) has not been decided. Split no further and start no package work until the user decides. A bundle whose inputs are one game's Records can't be shared; that is a known problem, not a pattern to copy.

## Pure

- A **Record** holds data and nothing else: named fields with values. A Record that holds instructions the game runs (`insn`, `jump`) holds logic and is impure.
- Only a Processor changes a Record (`../.github/CONTEXT.md`, Record): it takes the value out, computes, and may put the result back in the same place. The wires and guards order any two Processors that touch one place. A new Record is never needed just because a value changed (user, 2026-11-14).
- A **Processor** holds no state and names no Records. It is one file (`.runs-prim`) that takes values on its inputs (`in`, `inout`) and gives values on its outputs (`out`, `inout`); the Network wires a Record field to each (`../.github/CONTEXT.md`, Network).
- Every Record is a `game`, `interface`, or `presentation` Record: the Rules region, a boundary Record, or the Realization region. That split is the enduring-games pattern, a convention and not a RUNS primitive (`../.github/CONTEXT.md`, Processor); this project enforces it as its own rule. A Processor touches game and interface Records, or presentation and interface Records. Removing every presentation Processor leaves the game's Records the same at every step.
- The **Network** is one net: the game's colored Petri net, written as network files (`runs/**/*.net`) of places, transitions and arcs. Records are places, Processors are transitions. The order lives in the Network and nowhere else: the arcs and their guards write down which Processor fires after which, the order the original's steps ran in. Firing is parallel wherever no arc orders two Processors; where two could race on one place, a wire or a guard makes one wait for the other. A guard is part of an arc. It only tests values Records hold; a value it needs is computed by a Processor into a Record first. The guards on one place form a complete partition, exactly one true, with `when else` for an open-typed value (`../.github/CONTEXT.md`, Phase / Dispatch / Guard). A network may pass which slot to a transition (`name: routine(slot)`).

`INTENT.md` holds the model and the reasons; read its first two sections before you design anything. `../.github/CONTEXT.md` is the EGS vocabulary. Where a doc here disagrees with it, CONTEXT.md governs, unless the user has said otherwise more recently: then the user's newer word governs both, and CONTEXT.md gets fixed. Open questions the user hasn't decided stay open, even where CONTEXT.md reads as settled (`todo.md`, Open with the user).

## Every commit

Checks 1-4 exist to catch a change that breaks the image or the game; run them only when the commit changes something they read. `uv run -q python tools/gate_inputs.py` lists those changes: the RUNS source, the declarations, the sources, the oracle, and the tools `check_all.sh` reaches. Empty output (Markdown, `docs/`, a new report script nothing runs) means no check runs, and `check_all.sh` skips itself. A rule here that does nothing for its purpose in the case at hand is a defect to raise, not to follow. Every commit still gets its decisions row (5) and its push (6).

1. `uv run -q python tools/runsc.py | tail -1` prints `identical to the original` with sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
2. `tools/check_all.sh` passes. It prints each step's time and its own total; run it in the background and edit nothing under `runs/`, `pdp1/` or `tools/` while it runs.
3. The purity report stays at 0: `PYTHONPATH=tools uv run -q python tools/check_purity.py --against HEAD` exits 0.
4. The PDP-1 declarations do not grow: `uv run -q python tools/check_declarations.py` exits 0. It counts entries, not lines: every scalar value and every list element of the TOML (`pdp1/DECLARATIONS`, below).
5. A row in `docs/decisions.tsv` for each decision: what, why, evidence, result.
6. Push each verified commit to main: `git push origin HEAD:main`, fast-forward only (rebase on `origin/main` first if it moved). Standing order from the user; no need to ask. The same holds for every EGS repo this work touches (`../runs-spec`, `../.github` and the org's other repos): push each verified commit to its main without asking (user, 2026-11-11: "it's a general rule").

## Where a change goes

1. **The RUNS source.** The work lives here. Source that is hard to write means its shape is wrong: sketch at least two pure shapes and compile each.
2. **The compiler** (`tools/runsc.py`) is one general PDP-1 compiler for every PDP-1 program. It holds no game logic: no rule, limit or order that changes what happens in the game. Machine detail (registers, addresses, scratch words, the instructions that move a word) belongs here, not in the RUNS source (`../runs-spec/CONVERSION_PROCESS.md`, Rule or machine). A change is a general PDP-1 rule that a second PDP-1 program uses, never a fix to make one game's shape compile; its decisions row names the idiom and that program. The user: "there should be no changes at all to the compiler... Everything should be in how the network is structured" (2026-11-11, meaning no bending it for one game), "the compiler being a general pdp1 compiler" (2026-11-11), and "that's the job for the compiler to make sure that it runs on the PDP-1" (2026-11-14).
3. Neither works: stop and report the shapes tried and the evidence.

**The PDP-1 declarations** (`pdp1/*.toml`) are the half of the PDP-1 platform code that never runs. They record the 1962 programmer's arbitrary choices about where the game's data lives and how routines are called, nothing the game computes, and a Port leaves them behind with the PDP-1 presentation. Presentation Processors touch only interface Records; declarations may name game Records because they never run. They are not a place to solve what is hard to write in the source: `tools/check_declarations.py` fails any commit that adds an entry (a value, or a name added to an existing list, counts the same as a new line), and only the user raises the count in `pdp1/DECLARATIONS`, with the decisions row quoting the user. A commit that removes entries lowers it. The code still says `Bindings` and `BindError`; read them as the declarations.

Purity is fixed. When a pure shape will not compile to the original image, the shape stays pure and the work stops for a report.

## Converting one interaction

1. Read the original for it: `source/spacewar3.1_complete.txt`, the lift in `lift/`, and the current RUNS.
2. Sort every detail with one question: does changing it change anything that happens in the game? Yes: a rule, stated in the RUNS source (the arithmetic, limits, the order of two steps where swapping them changes a result, every glitch play reaches). No: the machine, left to the declarations or the compiler (registers, addresses, scratch words, order that changes nothing). `../runs-spec/CONVERSION_PROCESS.md`, Rule or machine.
3. Name the rules' data as Records, each with a kind, and the rules as Processors, each pure. Wire them into the Network in the order the original's steps run, one pull-change-put-back per step: a Processor takes a value from a Record, changes it, and puts it back; the next Processor takes it from there. Add no interim Record the original didn't have. Nothing computes between ticks: whatever the PDP-1 computed between two steps is a step in the Network.
4. Compile. When the image is identical to the original, run the checks of every commit. Otherwise try the next shape, then a general compiler rule, in the order above.
5. Done when the interaction is pure, the image matches, `check_all.sh` passes, and the purity report stays at 0.

## Evidence

- The game alone: `PYTHONPATH=tools uv run -q python tools/check_frame.py 300 alone` removes every presentation routine and Record and compares what is left with the whole program, frame by frame. A Record that differs is game work still living in a presentation Processor.
- Verify on the real artifact: the image, SIMH, the evaluator. A new check earns its place when a planted defect turns it red with the disagreement you predicted.
- The purity report is the progress meter. Every impurity stays on it until it is converted; a flag, marker, or exception that hides one from the report is the shortcut this project exists to refuse.
- A drawing or report is a transcription of the source: it shows what the files state, in the files' own structure.

## Where things are

- `todo.md`, the last round: the plan, the riskiest part, and where the work stands. Read it before the first change of a session.
- `pdp1/README.md`: the declarations' vocabulary and the rules `runsc` enforces. Read it before you change the declarations or the compiler.
- `../runs-spec`: the RUNS spec. `NETWORK_TOPOLOGY.md` (Records, kinds, Networks) and `CONVERSION_PROCESS.md` (how a conversion goes) bear on every unit. A language change lands there too, with examples that `../runs-spec/tools/check_examples.py ../runs-spec .` runs.
- `viewer/`: draws the RUNS source (`npm run net`, then `npm run dev`).

## Agent skills

### Issue tracker

GitHub issues on `wScottSh/runs-spacewar`, via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the root. See `docs/agents/domain.md`.
