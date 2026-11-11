# Standing orders: the Spacewar conversion

This repo converts Spacewar! 3.1 into **pure** RUNS. The conversion is a reorganization of the existing program (the PDP-1 assembly, and the C lift that builds the same image), never a re-vibe and never a rewrite of behavior. The RUNS source, compiled with the PDP-1 declarations, builds the original image at every commit.

## Pure

- A **Record** holds data and nothing else: named fields with values. A Record that holds instructions the game runs (`insn`, `jump`) holds logic and is impure.
- The vision writes a Record once and never overwrites it; a change is a fresh value in a fresh place (`../.github/CONTEXT.md` 90-92). Today's source updates Records in place, a gap.
- A **Processor** holds no state. In the vision it names no Records: it takes values on its inputs and gives values on its outputs, and the Network wires a Record Field to each (`../.github/CONTEXT.md` 166-169). Today every Processor in `runs/` still declares the Records it reads and writes (`reads:`, `writes:`), and none has an input or output line yet, a gap.
- Every Record is a `game`, `interface`, or `presentation` Record: the Rules region, a boundary Record, or the Realization region. That split is the enduring-games pattern, a convention and not a RUNS primitive (`../.github/CONTEXT.md` 131-135, 158-160); this project enforces it as its own rule. A Processor touches game and interface Records, or presentation and interface Records. Removing every presentation Processor leaves the game's Records the same at every step.
- The **Network** is one net: the game's colored Petri net, Records as places and Processors as transitions. In the vision it is the explicit bipartite wiring of Records to Processors, and execution order is derived from that wiring, never authored (`../.github/CONTEXT.md` 162-170, 188-199). The Network as written today is structured code (`if`, `loop`, `break`) that states the original's order line by line; it falls short of the graph. A guard only tests values Records hold; a value it needs is computed by a Processor into a Record first. The vision's guards also form a complete partition, exactly one true, with an explicit `else` for an open-typed value (`../.github/CONTEXT.md` 351-358); today's source has `if` with no `else`, a gap. A `run` passes only which slot.

`INTENT.md` holds the model and the reasons; read its first two sections before you design anything. The EGS vision is `../.github/CONTEXT.md`; where a doc here disagrees with it, the vision governs.

## Every commit

Checks 1-4 exist to catch a change that breaks the image or the game; run them only when the commit changes something they read. `uv run -q python tools/gate_inputs.py` lists those changes: the RUNS source, the declarations, the sources, the oracle, and the tools `check_all.sh` reaches. Empty output (Markdown, `docs/`, a new report script nothing runs) means no check runs, and `check_all.sh` skips itself. A rule here that does nothing for its purpose in the case at hand is a defect to raise, not to follow. Every commit still gets its decisions row (5) and its push (6).

1. `uv run -q python tools/runsc.py | tail -1` prints `MATCH` with sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
2. `tools/check_all.sh` passes. It prints each step's time and its own total; run it in the background and edit nothing under `runs/`, `pdp1/` or `tools/` while it runs.
3. The purity report gains no line: `PYTHONPATH=tools uv run -q python tools/check_purity.py --against HEAD` exits 0. It allows a new line only where a Record just got its kind and revealed an impurity already there; the decisions row lists those.
4. The PDP-1 declarations do not grow: `uv run -q python tools/check_declarations.py` exits 0. It counts entries, not lines: every scalar value and every list element of the TOML (`pdp1/DECLARATIONS`, below).
5. A row in `docs/decisions.tsv` for each decision: what, why, evidence, result.
6. Push each verified commit to main: `git push origin HEAD:main`, fast-forward only (rebase on `origin/main` first if it moved). Standing order from the user; no need to ask. The same holds for `../runs-spec` (`enduring-game-standard/runs-spec`): push each verified spec commit to its main without asking (user, 2026-11-11: "it's a general rule").

## Where a change goes

1. **The RUNS source.** The work lives here. Source that is hard to write means its shape is wrong: sketch at least two pure shapes and compile each.
2. **The compiler** (`tools/runsc.py`), only when no pure shape compiles. It is the one PDP-1 back end for every PDP-1 game. A change is a rule a second PDP-1 program uses, and its decisions row names the idiom and that program.
3. Neither works: stop and report the shapes tried and the evidence.

**There is no binding.** What used to be called the binding is the PDP-1 package's declarations (`pdp1/*.toml`): the half of the PDP-1 platform code that never runs. It records the 1962 programmer's arbitrary choices about where the game's data lives and how routines are called, nothing the game computes, and a port leaves it behind with the PDP-1 presentation. Presentation Processors touch only interface Records; declarations may name game Records because they never run. They are not a place to solve what is hard to write in the source: `tools/check_declarations.py` fails any commit that adds an entry (a value, or a name added to an existing list, counts the same as a new line), and only the user raises the count in `pdp1/DECLARATIONS`, with the decisions row quoting the user. A commit that removes entries lowers it. The code still says `Bindings` and `BindError`; read them as the declarations.

Purity is fixed. When a pure shape will not compile to the original image, the shape stays pure and the work stops for a report.

## Converting one interaction

1. Read the original for it: `source/spacewar3.1_complete.txt`, the lift in `lift/`, and the current RUNS.
2. Name its data as Records, each with a kind, and its rules as Processors, each pure.
3. Wire them into the Network. The Network as written today states them in the original's order (see Pure).
4. Compile. On `MATCH`, run the checks of every commit. Otherwise try the next shape, then a general compiler rule, in the order above.
5. Done when the interaction is pure, the image matches, `check_all.sh` passes, and the purity count fell.

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
