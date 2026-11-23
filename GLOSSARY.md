# Spacewar! 3.1 in RUNS

Spacewar! 3.1 (1962 PDP-1 assembly) converted to RUNS, exactly: the same game over every sequence of inputs from power-on, with its Game Logic stated completely so its Glitches emerge as they did on the PDP-1. Nothing is asserted about the game that was not checked against the original running as itself.

## Language

### Authorities

**Ground Truth**:
The original PDP-1 assembly (`source/spacewar3.1_complete.txt`), executed as itself. The sole authority on what Spacewar does.
_Avoid_: spec, reference, the original (when it could mean the listing, the image or the 1962 program)

**Translator**:
Norbert Landsteiner's "Inside Spacewar!" notes (`source/masswerk/`). A guide to what a routine does and how to read a value, never an authority: it can be wrong about Ground Truth.
_Avoid_: spec, documentation (unqualified)

### The conversion

**Conversion**:
Rewriting the original program into RUNS while the game stays exactly the same: the reference every later Port and Variant starts from (`../.github/GLOSSARY.md`, Conversion). Its Game Logic is pure and separate from the Presentation, and the whole original Presentation is still there: compiled for the PDP-1 it is the original game; run headless its Game Logic runs alone on any machine.
_Avoid_: Port, Variant, re-vibe

**RUNS source**:
The game written in RUNS: Records, Processors and Networks. It is the game. It executes in the Evaluator and compiles to the Image.
_Avoid_: RUNS Conversion, Realization, translation, RUNS text

**Record**:
Anything the game remembers, one value or a fixed-size collection. All game state is Records, globals included. Only a Processor changes a Record: it takes the value out, computes, and may put the result back in the same place (`../.github/GLOSSARY.md`, Record). A Record holds data only, never logic.
_Avoid_: global, variable, state (unqualified)

**Processor**:
One stateless step, one `.runs-prim` file. It names no Records: its whole contract is its inputs and outputs, and the Network wires a Record Field to each at each use (`../.github/GLOSSARY.md`, Network).
_Avoid_: function, subroutine (except for the Original's `jda` routines)

**Input, output**:
One value a Routine takes in, gives out, or both, with the kind of value it is: the source's `in name: kind`, `out name: kind` and `inout name: kind` lines. At each use the Network wires it to one Field of a Record, a single slot of that Field by default, or the whole Field when the Routine indexes it itself. The rule is one input or output, one Field, so every wire is written in the Network. 21 Network inputs and outputs take the whole object table (`inout table: objects`); the user calls a bundle whose inputs are one game's Records a problem, and how to fix it is open. Routines with the same inputs and outputs can be swapped. The code still calls them ports (`expand_ports`, `prog.ports`).
_Avoid_: port (EGS keeps the word for the same game on other hardware, `../.github/GLOSSARY.md`, Port), parameter, argument, pin, binding (say the Network wires a Field to an input or output)

**Port**:
The same game, its Game Logic untouched, run on other hardware by swapping its Presentation (`../.github/GLOSSARY.md`, Port). Swapping out the PDP-1 Presentation is a Port; the Declarations, which never run, are left behind with it (Declarations, below).
_Avoid_: port for a Routine's input or output; Port for this conversion (it is a Conversion)

**Network**:
The game's skeleton, written as Network files (`runs/**/*.net`): places, transitions and the arcs between them, a colored Petri net (`../.github/GLOSSARY.md`, Network). The arcs and their Guards write down the order; nothing else holds it. A Guard tests a value a Record holds and is part of its arc. Only the Network that walks the slots holds slot numbers; a slot the game computes lives in a Record.
_Avoid_: scheduler, main loop (when it means the Network, not the original's code)

**Routine**:
A Processor or a Network.
_Avoid_: calc routine (that is a game term, below)

**Top Network**:
A Network nothing fires. Its `requires:` and `produces:` lines name its inputs and outputs, what the world writes before a tick and reads after. Spacewar has three: `tick`, which the Host fires once a tick, and two Start Networks. `requires:` also still states a Precondition in two files (`requires: slot < 2`), a second meaning of one keyword.

**Start Network**:
The Top Network the Host fires once when the operator starts the machine, chosen by the start address (4 or 5).

**Tick**:
One firing of `tick` (`runs/game/tick.net`): a frame of play, one pass of the original's main loop from `ml0` to its jump back, or, after the halt that shows the scores, the operator's answer (`pause.phase` says which). The Frame seam, where a check compares state, is the start of a frame. Nothing computes between ticks.
_Avoid_: step

**Host**:
Whatever fires the Top Networks. It writes the top Networks' inputs before a tick and reads their outputs after.
_Avoid_: driver

**Unknown Field**:
A Field with no initial value. It is unknown until the game sets it or the world gives it, and reading it while unknown is an error. The console's switches and the words core held at power-on are Unknown Fields.

**Presentation**:
Everything in the game that is not Game Logic or an Interface Record: the code that reads the controls and drives the scope and the pacing. Its Records have the Kind `presentation`, as `game` marks the Game Logic and `interface` an Interface Record. Kinds are a convention, not a RUNS primitive (`../.github/GLOSSARY.md`, Presentation and Kind).
_Avoid_: rendering, I/O (unqualified)

**Glitch**:
Gameplay that emerges from the Game Logic, which the designer did not foresee. A Glitch is not Game Logic of its own. The Conversion states the Game Logic completely, including how the program's own operations behave on the PDP-1 (its arithmetic, memory past an array, code the program writes for itself), and Glitches emerge from it; it neither recreates nor removes one. A behavior is sorted by following its data across the PDP-1's edge, never by intent: what comes in from a device or from core the program never set is an input, a value that only flows out to the scope is Presentation, and everything else is Game Logic (`../.github/GLOSSARY.md`, Glitch).
_Avoid_: bug (when it means the original's behavior); "recreate" or "purge" a Glitch; intended or unintended as a test

**Variant**:
A deliberate change to the Game Logic: an edit to one Processor or one Network line, and the game that results (`../.github/GLOSSARY.md`, Variant).
_Avoid_: house rule; mod; fork for the result (`../.github/GLOSSARY.md`, Variant)

**Bound**:
What stops a loop: a counter. Each loop in the source is written as a loop bundle (a Network file with a `counter` line): each pass takes one token of the counter, and the loop ends when it reaches its end or a Guard stops it. Every loop must be bounded by something; it is a rule for the whole graph, and a loop need not live in a bundle (user, 2026-11-14); the loader reads only the bundle form so far. The only unbounded loop is the game itself, tick after tick.

### Toolchain

**SIMH**:
The reference PDP-1 simulator, running the Oracle image. Its CPU semantics are frozen: we observe how it computes and never alter it.
_Avoid_: Substrate (EGS keeps the word for the RUNS source itself, `../.github/GLOSSARY.md`, Neutral Substrate; the ADRs still call SIMH the Substrate), emulator (unqualified), VM

**Assembler**:
`macro1`, the canonical PDP-1 Macro assembler. It turns Ground Truth into the Oracle image and the listing whose symbols name where each routine and word lives.
_Avoid_: compiler

**Evaluator**:
The program that parses the RUNS source, checks it statically, then runs it: a runtime in the sense of `../.github/GLOSSARY.md`, Flagged ambiguities, not a hand-compilation.
_Avoid_: interpreter, emulator, reference implementation (`../.github/GLOSSARY.md`, Flagged ambiguities keeps that for a blessed body)

**Compiler**:
`runsc`. It turns the RUNS source and the Declarations into the Compiled image, by way of the lift's C dialect (`docs/c-lift/README.md`).
_Avoid_: assembler, transpiler

**Declarations**:
The half of one platform's package that never runs (`pdp1/*.toml` for the PDP-1): where that machine keeps each value and how it calls each routine, tape order, devices. They record the original programmer's arbitrary choices, never Game Logic, and they may name game Records because they never run. A Port leaves them behind with that platform's Presentation. They only shrink (`tools/check_declarations.py`).
_Avoid_: binding (retired: it read as a layer to solve what is hard to write in RUNS), mapping, layout (layout play reads belongs to the RUNS source)

**Image**:
The tape image (`.rim`) the PDP-1 loads. The **Oracle image** is the Assembler's output from Ground Truth. The **Compiled image** is the Compiler's output from the RUNS source. The two must have the same sha256.
_Avoid_: binary (unqualified), tape, ROM

### Verification

**Oracle**:
The original binary. The RUNS source, compiled with the Declarations, rebuilds the Oracle image byte for byte (same sha256). Comparing play proves only the inputs tested; the identical image proves every input, Presentation included (`../.github/GLOSSARY.md`, Conversion). The user, 2026-11-15: "The only way for an oracle to prove that it is exactly the same is that when you compile it, it becomes the exact same binary again." The Checks and the Mutation check are how the work gets there and stays there: evidence, not the oracle. ADR-0014's "no finite suite proves equivalence" is about Checks, not the image.

**Check**:
A comparison of one Routine fired in the Evaluator with Ground Truth running in SIMH, on the same Records.
_Avoid_: test (unqualified), oracle

**Vector**:
A recorded input→output pair of raw words for one of the Original's `jda` routines, observed from SIMH, never hand-derived.
_Avoid_: test case, fixture, golden

**Mutation check**:
The check that every edit to the RUNS source or the Declarations changes the Compiled image, is refused, or is shown to be the Same game.
_Avoid_: the gate (unqualified), fuzzing

**Same game**:
The judgment that a mutant which still builds the original Image changes nothing play can see: fired before and after on the same Records, it gives the same Records, points and errors. It is evidence, not proof.
_Avoid_: equivalent (unqualified), proven

**Gate**:
The objective bar for "verified": the image hashes match, the sampled Mutation check passes, and every Check matches.
_Avoid_: CI, done (when it means someone's say-so)

### The game

**Object table**:
The Record of every moving thing: two spaceships, then 22 torpedoes. Each entry is a Slot.

**Slot**:
An index into the Object table. Slots 0 and 1 are the spaceships.

**Calc routine**:
The routine that moves one object for a frame: spaceship, torpedo, explosion, in hyperspace, breakout. Each entry's routine word names it, and the name fixes whether the object collides.

**Control word**:
A spaceship's input for a frame, read from the test word switches or the control boxes, as the start address chose.

**Tunables**:
The Original's "interesting and often changed constants" at the head of the tape. Some are numbers in a Record. Others are instructions the original executes, which are Processors.

**Outline**:
A spaceship's shape (the needle and the wedge). At each new game the outline compiler turns it into instructions, which the spaceship runs each frame to draw itself. Presentation.

## Flagged ambiguities

- **"Oracle"** means the original binary (the Oracle image). The oracle listing and the `oracle/` Vectors are named so, never "the oracle".
- **"Source"** can mean Ground Truth, the Translator's notes in `source/`, or the RUNS source. Always qualify it.
- **"Gate"**: ADR-0011 and ADR-0017 mean the Gate as defined here. `INTENT.md`'s "full gate" means the full Mutation check, which runs by hand.
- **"Tunables"** names both the Record of numbers and the Processors the original executes with `xct`.

## Retired terms

These come from the earlier verification method. They appear in ADRs 0001–0016, which ADR-0017 supersedes or amends.

- **Oracle** (as a suite), **Portable Oracle**, **Trace**, **Pinned inputs**, **Coverage** (as the definition of done): the JS Oracle harness and its coverage gate, removed.
- **RUNS Conversion**: the RUNS source, back when it could not execute.
- **Realization**, **Exact Realization**, **Variant**: a playable recreation built from the Conversion. The RUNS source plays now. A deliberate change is a Variant. Realization and Variant now carry their EGS senses (`../.github/GLOSSARY.md`, Processor and Variant); only the old sense is retired.

## Example dialogue

> **Dev:** The gravity code in the spaceship is written. Is it done?
> **Expert:** Does the spaceship Check match?
> **Dev:** I read the Translator's gravity page and it matches what that says.
> **Expert:** That's the Translator, not Ground Truth. It can be wrong. Done means the Evaluator fired your spaceship and SIMH ran the Original on the same Records, and every word and point matched. Then the Gate: the Compiled image still hashes to the Oracle image, and the Mutation check passes.
> **Dev:** It matches. So the conversion is proven right?
> **Expert:** Only if the image compiled from it is still byte-for-byte the Original. That is the oracle; the Checks show where to look when it isn't.
