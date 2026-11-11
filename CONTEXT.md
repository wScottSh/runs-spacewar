# Spacewar! 3.1 in RUNS

Spacewar! 3.1 (1962 PDP-1 assembly) written in RUNS, verbatim: the same game over every sequence of inputs from power-on, glitches included. Nothing is asserted about the game that was not checked against the original running as itself.

## Language

### Authorities

**Ground Truth**:
The original PDP-1 assembly (`source/spacewar3.1_complete.txt`), executed as itself. The sole authority on what Spacewar does.
_Avoid_: spec, reference, the original (when it could mean the listing, the image or the 1962 program)

**Translator**:
Norbert Landsteiner's "Inside Spacewar!" notes (`source/masswerk/`). A guide to what a routine does and how to read a value, never an authority: it can be wrong about Ground Truth.
_Avoid_: spec, documentation (unqualified)

### The port

**RUNS text**:
The game written in RUNS: Records, Processors and Networks. It is the game. It executes in the Evaluator and compiles to the Image.
_Avoid_: RUNS Conversion, Realization, translation, RUNS source

**Record**:
Anything the game remembers, one value or a fixed-size collection. All game state is Records, globals included.
_Avoid_: global, variable, state (unqualified)

**Processor**:
One rule, stateless. It names no Records: its whole contract is its Ports, and the Network wires Records to them at each use.
_Avoid_: function, subroutine (except for the original's `jda` routines)

**Port**:
One value a Routine takes in, gives out, or both, with the kind of value it is. At each use the Network wires it to one field of a Record, a single slot of that field by default, or the whole field when the Routine indexes it itself. Routines with the same Ports can be swapped.
_Avoid_: parameter (that is a slot passed by `run`), argument, pin, binding (say the Network wires a field to a Port)

**Network**:
The game's skeleton. It fires Processors and other Networks in order, wires Records to their Ports, chooses with guards, iterates with bounds, and writes nothing. Only the Top Networks name Records; a Network below them has Ports of its own and passes them down.
_Avoid_: scheduler, main loop (when it means the Network, not the original's code)

**Routine**:
A Processor or a Network.
_Avoid_: calc routine (that is a game term, below)

**Top Network**:
A Network nothing fires. Its contract is the game's boundary with presentation. Spacewar has three: two Start Networks and the frame.

**Start Network**:
The Top Network the Host fires once when the operator starts the machine, chosen by the start address (4 or 5).

**Frame**:
One firing of the frame Top Network: one pass of the original's main loop, from `ml0` to its jump back. The Frame seam, where a check compares state, is its start.
_Avoid_: tick, step

**Host**:
Whatever fires the Top Networks and serves a `wait`. It shows what leaves the game and supplies what comes in.
_Avoid_: runtime, driver

**Unknown field**:
A field with no initial value. It is unknown until the game sets it or the world gives it, and reading it while unknown is an error. The console's switches and the words core held at power-on are Unknown fields.

**Presentation**:
Code whose effects nothing in the game can observe: the screen, the controls, the pacing. What a piece of code is decides by what its effects reach, not by what it was written for.
_Avoid_: rendering, I/O (unqualified)

**Glitch**:
Behavior the original has that its authors did not intend. It is part of the game, and the port keeps it. By what it reads, a glitch is a logic, a layout or a machine glitch.
_Avoid_: bug (when it means the original's behavior)

**House rule**:
A deliberate change to the game: an edit to one Processor or one Network line.
_Avoid_: Variant, mod, fork

**Bound**:
The most times a loop or a `jump` may run, stated in the RUNS text. It is RUNS's check on the port, not a rule of the game, and it compiles to nothing.

### Toolchain

**Substrate**:
SIMH, the reference PDP-1 simulator, running the Oracle image. Its CPU semantics are frozen: we observe how it computes and never alter it.
_Avoid_: emulator (unqualified), VM

**Assembler**:
`macro1`, the canonical PDP-1 Macro assembler. It turns Ground Truth into the Oracle image and the listing whose symbols name where each routine and word lives.
_Avoid_: compiler

**Evaluator**:
The reference implementation of RUNS. It checks the RUNS text statically, then runs it.
_Avoid_: interpreter, emulator

**Compiler**:
`runsc`. It turns the RUNS text and the Declarations into the Compiled image, by way of the lift's C dialect (`docs/c-lift/README.md`).
_Avoid_: assembler, transpiler

**Declarations**:
The half of one platform's package that never runs (`pdp1/*.toml` for the PDP-1): where that machine keeps each value and how it calls each routine, tape order, devices. They record the original programmer's arbitrary choices, never game logic, and they may name game Records because they never run. A port leaves them behind with that platform's presentation. They only shrink (`tools/check_declarations.py`).
_Avoid_: binding (retired: it read as a layer to solve hard text in), mapping, layout (layout play reads belongs to the RUNS text)

**Image**:
The tape image (`.rim`) the PDP-1 loads. The **Oracle image** is the Assembler's output from Ground Truth. The **Compiled image** is the Compiler's output from the RUNS text. The two must have the same sha256.
_Avoid_: binary (unqualified), tape, ROM

### Verification

**Check**:
A comparison of one Routine fired in the Evaluator with Ground Truth running in the Substrate, on the same Records.
_Avoid_: test (unqualified), oracle

**Vector**:
A recorded input→output pair of raw words for one of the original's `jda` routines, observed from the Substrate, never hand-derived.
_Avoid_: test case, fixture, golden

**Mutation check**:
The check that every edit to the RUNS text or the Declarations changes the Compiled image, is refused, or is shown to be the Same game.
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

- **"Oracle"** now means three things: the Oracle image, the oracle listing, and the `oracle/` directory of Vectors. It no longer means a test suite (ADR-0017). Qualify it every time.
- **"Source"** can mean Ground Truth, the Translator's notes in `source/`, or the RUNS text. Always qualify it.
- **"Gate"**: ADR-0011 and ADR-0017 mean the Gate as defined here. `INTENT.md`'s "full gate" means the full Mutation check, which runs by hand.
- **"Tunables"** names both the Record of numbers and the Processors the original executes with `xct`.
- **Verified ≠ proven equivalent (ADR-0014).** A passing Gate is evidence. No finite set of Checks proves the RUNS text is the original over unbounded play, and Bounds and Same-game judgments are not proofs. Do not reopen this as a backlog item.

## Retired terms

These come from the earlier verification method. They appear in ADRs 0001–0016, which ADR-0017 supersedes or amends.

- **Oracle** (as a suite), **Portable Oracle**, **Trace**, **Pinned inputs**, **Coverage** (as the definition of done): the JS Oracle harness and its coverage gate, removed.
- **RUNS Conversion**: the RUNS text, back when it could not execute.
- **Realization**, **Exact Realization**, **Variant**: a playable recreation built from the Conversion. The RUNS text plays now. A deliberate change is a House rule.

## Example dialogue

> **Dev:** The gravity code in the spaceship is written. Is it done?
> **Expert:** Does the spaceship Check match?
> **Dev:** I read the Translator's gravity page and it matches what that says.
> **Expert:** That's the Translator, not Ground Truth. It can be wrong. Done means the Evaluator fired your spaceship and SIMH ran the original on the same Records, and every word and point matched. Then the Gate: the Compiled image still hashes to the Oracle image, and the Mutation check passes.
> **Dev:** It matches. So the port is proven right?
> **Expert:** It's verified, which is evidence. Proof that it's the same game over all play is impossible (ADR-0014).
