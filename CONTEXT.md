# Spacewar! 3.1 in RUNS

Spacewar! 3.1 (1962 PDP-1 assembly) converted to RUNS, exactly: the same game over every sequence of inputs from power-on, glitches included. Nothing is asserted about the game that was not checked against the original running as itself.

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
Rewriting the original program into RUNS while the game stays exactly the same: the reference every later Port and Variant starts from (`../.github/CONTEXT.md`, Conversion). Its rules are pure and separate from the presentation, and the whole original presentation is still there: compiled for the PDP-1 it is the original game; run headless its rules run alone on any machine.
_Avoid_: port, variant, re-vibe

**RUNS source**:
The game written in RUNS: Records, Processors and Networks. It is the game. It executes in the Evaluator and compiles to the Image.
_Avoid_: RUNS Conversion, Realization, translation, RUNS text

**Record**:
Anything the game remembers, one value or a fixed-size collection. All game state is Records, globals included. Only a Processor changes a Record: it takes the value out, computes, and may put the result back in the same place (`../.github/CONTEXT.md`, Record). A Record holds data only, never logic.
_Avoid_: global, variable, state (unqualified)

**Processor**:
One rule, stateless, one `.runs-prim` file. It names no Records: its whole contract is its inputs and outputs, and the Network wires a Record field to each at each use (`../.github/CONTEXT.md`, Network).
_Avoid_: function, subroutine (except for the original's `jda` routines)

**Input, output**:
One value a Routine takes in, gives out, or both, with the kind of value it is: the source's `in name: kind`, `out name: kind` and `inout name: kind` lines. At each use the Network wires it to one field of a Record, a single slot of that field by default, or the whole field when the Routine indexes it itself. The rule is one input or output, one field, so every wire is written in the Network. Today 21 network inputs and outputs take a whole Record (`inout table: objects`); the user calls a bundle whose inputs are one game's Records a problem, and how to fix it is open. Routines with the same inputs and outputs can be swapped. The code still calls them ports (`expand_ports`, `prog.ports`).
_Avoid_: Port (EGS keeps the word for the same game on other hardware, `../.github/CONTEXT.md` 330-356), parameter, argument, pin, binding (say the Network wires a field to an input or output)

**Port**:
The same game, its Rules region untouched, run on other hardware by swapping its Realization Processors (`../.github/CONTEXT.md` 330-356). Swapping out the PDP-1 presentation is a Port; the Declarations, which never run, are left behind with it (Declarations, below).
_Avoid_: port for a Routine's input or output; port for this conversion (it is a Conversion)

**Network**:
The game's skeleton, written as network files (`runs/**/*.net`): places, transitions and the arcs between them, a colored Petri net (`../.github/CONTEXT.md`, Network). The arcs and their guards write down the order; nothing else holds it. A guard tests a value a Record holds and is part of its arc. Only the Network that walks the slots holds slot numbers; a slot the game computes lives in a Record.
_Avoid_: scheduler, main loop (when it means the Network, not the original's code)

**Routine**:
A Processor or a Network.
_Avoid_: calc routine (that is a game term, below)

**Top Network**:
A Network nothing fires. Its `requires:` and `produces:` lines name the boundary Records, what the world writes before a tick and reads after (`../.github/CONTEXT.md`, Boundary Record). Spacewar has three: `tick`, which the Host fires once a tick, and two Start Networks. `requires:` also still states a precondition in two files (`requires: slot < 2`), a second meaning of one keyword.

**Start Network**:
The Top Network the Host fires once when the operator starts the machine, chosen by the start address (4 or 5).

**Tick**:
One firing of `tick` (`runs/game/tick.net`): a frame of play, one pass of the original's main loop from `ml0` to its jump back, or, after the halt that shows the scores, the operator's answer (`pause.phase` says which). The Frame seam, where a check compares state, is the start of a frame. Nothing computes between ticks.
_Avoid_: step

**Host**:
Whatever fires the Top Networks. It writes the inbound boundary Records before a tick and reads the outbound ones after (`../.github/CONTEXT.md`, Runtime).
_Avoid_: driver

**Unknown field**:
A field with no initial value. It is unknown until the game sets it or the world gives it, and reading it while unknown is an error. The console's switches and the words core held at power-on are Unknown fields.

**Presentation**:
Code whose effects nothing in the game can observe: the screen, the controls, the pacing. What a piece of code is decides by what its effects reach, not by what it was written for. Its Records are marked `presentation`: the Realization region, as `game` marks the Rules region and `interface` a boundary Record. That every Record carries one of these kinds is this project's rule, after the enduring-games pattern, not a RUNS primitive (`../.github/CONTEXT.md` 131-135, 158-160).
_Avoid_: rendering, I/O (unqualified)

**Glitch**:
Behavior the original has that its authors did not intend. It is part of the game, and the conversion keeps it. By what it reads, a glitch is a logic, a layout or a machine glitch.
_Avoid_: bug (when it means the original's behavior)

**House rule**:
A deliberate change to the game: an edit to one Processor or one Network line. EGS calls the resulting game a Variant (`../.github/CONTEXT.md` 405-411).
_Avoid_: mod; fork for the result (`../.github/CONTEXT.md` 427-429)

**Bound**:
What stops a loop. Each loop of a Network is a loop bundle (a network file with a `counter` line): each pass takes one token of the counter, and the loop ends when it reaches its end or a guard stops it. Every loop must be bounded by something; whether loops must live in bundles is open with the user. The only unbounded loop is the game itself, tick after tick.

### Toolchain

**SIMH**:
The reference PDP-1 simulator, running the Oracle image. Its CPU semantics are frozen: we observe how it computes and never alter it.
_Avoid_: Substrate (EGS keeps the word for the RUNS source itself, `../.github/CONTEXT.md` 79-86; the ADRs still call SIMH the Substrate), emulator (unqualified), VM

**Assembler**:
`macro1`, the canonical PDP-1 Macro assembler. It turns Ground Truth into the Oracle image and the listing whose symbols name where each routine and word lives.
_Avoid_: compiler

**Evaluator**:
The program that parses the RUNS source, checks it statically, then runs it: a runtime in the sense of `../.github/CONTEXT.md` 478-480, not a hand-compilation.
_Avoid_: interpreter, emulator, reference implementation (`../.github/CONTEXT.md` 483-491 keeps that for a blessed body)

**Compiler**:
`runsc`. It turns the RUNS source and the Declarations into the Compiled image, by way of the lift's C dialect (`docs/c-lift/README.md`).
_Avoid_: assembler, transpiler

**Declarations**:
The half of one platform's package that never runs (`pdp1/*.toml` for the PDP-1): where that machine keeps each value and how it calls each routine, tape order, devices. They record the original programmer's arbitrary choices, never game logic, and they may name game Records because they never run. A port leaves them behind with that platform's presentation. They only shrink (`tools/check_declarations.py`).
_Avoid_: binding (retired: it read as a layer to solve what is hard to write in RUNS), mapping, layout (layout play reads belongs to the RUNS source)

**Image**:
The tape image (`.rim`) the PDP-1 loads. The **Oracle image** is the Assembler's output from Ground Truth. The **Compiled image** is the Compiler's output from the RUNS source. The two must have the same sha256.
_Avoid_: binary (unqualified), tape, ROM

### Verification

**Oracle**:
The original binary. The RUNS source, compiled with the Declarations, rebuilds the Oracle image byte for byte (same sha256). Comparing play proves only the inputs tested; the identical image proves every input, presentation included (`../.github/CONTEXT.md`, Conversion). The Checks and the Mutation check are how the work gets there and stays there, not the oracle.

**Check**:
A comparison of one Routine fired in the Evaluator with Ground Truth running in SIMH, on the same Records.
_Avoid_: test (unqualified), oracle

**Vector**:
A recorded input→output pair of raw words for one of the original's `jda` routines, observed from SIMH, never hand-derived.
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
The rule that moves one object for a frame: spaceship, torpedo, explosion, in hyperspace, breakout. Each entry's routine word names it, and the name fixes whether the object collides.

**Control word**:
A spaceship's input for a frame, read from the test word switches or the control boxes, as the start address chose.

**Tunables**:
The original's "interesting and often changed constants" at the head of the tape. Some are numbers in a Record. Others are instructions the original executes, which are Processors.

**Outline**:
A spaceship's shape (the needle and the wedge). At each new game the outline compiler turns it into instructions, which the spaceship runs each frame to draw itself. Presentation.

## Flagged ambiguities

- **"Oracle"** means the original binary (the Oracle image). The oracle listing and the `oracle/` Vectors are named so, never "the oracle".
- **"Source"** can mean Ground Truth, the Translator's notes in `source/`, or the RUNS source. Always qualify it.
- **"Gate"**: ADR-0011 and ADR-0017 mean the Gate as defined here. `INTENT.md`'s "full gate" means the full Mutation check, which runs by hand.
- **"Tunables"** names both the Record of numbers and the Processors the original executes with `xct`.
- **Checks are evidence; the image is the proof.** A passing Check proves the inputs it ran. The identical image is what the user names as the proof (2026-11-15: "The only way for an oracle to prove that it is exactly the same is that when you compile it, it becomes the exact same binary again"). ADR-0014's "no finite suite proves equivalence" is about Checks, not the image.

## Retired terms

These come from the earlier verification method. They appear in ADRs 0001–0016, which ADR-0017 supersedes or amends.

- **Oracle** (as a suite), **Portable Oracle**, **Trace**, **Pinned inputs**, **Coverage** (as the definition of done): the JS Oracle harness and its coverage gate, removed.
- **RUNS Conversion**: the RUNS source, back when it could not execute.
- **Realization**, **Exact Realization**, **Variant**: a playable recreation built from the Conversion. The RUNS source plays now. A deliberate change is a House rule. Realization and Variant now carry their EGS senses (`../.github/CONTEXT.md` 136-142, 405-411); only the old sense is retired.

## Example dialogue

> **Dev:** The gravity code in the spaceship is written. Is it done?
> **Expert:** Does the spaceship Check match?
> **Dev:** I read the Translator's gravity page and it matches what that says.
> **Expert:** That's the Translator, not Ground Truth. It can be wrong. Done means the Evaluator fired your spaceship and SIMH ran the original on the same Records, and every word and point matched. Then the Gate: the Compiled image still hashes to the Oracle image, and the Mutation check passes.
> **Dev:** It matches. So the conversion is proven right?
> **Expert:** Only if the image compiled from it is still byte-for-byte the original. That is the oracle; the Checks show where to look when it isn't.
