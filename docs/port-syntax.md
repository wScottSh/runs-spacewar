# Syntax for inputs, outputs and their wiring

Decided with the user, 2026-11-11, in "Syntax for Ports and their wiring in the RUNS
text" (#52). The spec text and a runnable example land with "Ports in the Evaluator
and runsc" (#53), when the Evaluator reads this syntax.

The issues and this file's name say Port for a Routine's input or output.
EGS keeps Port for the same game on other hardware, made by swapping its Realization
Processors (`../../.github/CONTEXT.md` 313-339). The text below says input and output.

## The syntax

An input or output is a header line, `direction name: kind`, the same on a Processor
and on a Network. It replaces `reads:`/`writes:`, which every Routine in `runs/` that
names a Record still uses; none there has an input or output line yet. A `run` wires
one input or output per indented line. A same-name wire (`velocity: velocity`) may
be left out.

```
processor clear                                             # cla
  out value: word
  set value = 0

processor inertia                                           # diff
  in acceleration: word
  inout velocity: word
  inout position: word
  out moved: word                                           # left in AC
  let v = acceleration + velocity
  set velocity = v
  set moved = (v >> 3) + position
  set position = moved

network drift                                               # cla; diff
  inout velocity: word
  inout position: word
  out moved: word
  owns acceleration: word                                   # scratch: only drift touches it
  run clear
    value: acceleration
  run inertia
    acceleration: acceleration
    velocity: velocity
    position: position
    moved: moved

network explosion                                           # mex
  inout x: word
  inout y: word
  inout dx: word
  inout dy: word
  out moved: word
  ...
  run drift
    velocity: dx
    position: x
  run drift
    velocity: dy
    position: y
  ...
```

`owns name: kind` declares one field of scratch, as an input or output line declares one field
(#53). The Evaluator keeps one copy of it for the Network, shared by every wiring of
the Network; no name in the text reaches it from outside. `runsc` compiles it as a
local of the routine the Network compiles into, declared once, so pdp1cc keeps it in
AC or IO with no declaration (#51; until then it was refused). A declaration names it
as it names a `let` (`io = ["input_bits"]`).

## How the tools read it (#53)

The loader (`runs.load`) expands inputs and outputs (`expand_ports`) before any tool
sees the program. Each `run` of a routine with inputs and outputs fires a copy of it:
its text with each replaced by the field the run wires to it, by reference, as the
original's `diff` macro was expanded once an axis. One copy a distinct wiring
(`inertia_1`, `inertia_2`); a Network's input or output wired on to an inner `run`
resolves to the field of the Network that runs it. A copy takes the names its wires'
slots use (`slot`) from the routine that runs it. The Program keeps the templates
(`templates`) and each copy's template and wiring (`copies`); the purity report judges
the copies by the Records they touch.

A PDP-1 declaration that names a template declares every copy of it: `[[inline]]
routine = "inertia"` lays out both axes' copies. A called routine (`[[place]]`, JDA or
JSP) is one subroutine, so all its runs must share one wiring; more is a BindError that
names the wirings. Minskytron's `keep` (six wirings, laid out inline) is the second
PDP-1 program; `tools/check_ports_scratch.py` builds Spacewar with one
`inertia` that has inputs and outputs and prints the original's `MATCH`.

## The rules

1. **Header lines, one wire per line** (over parens like a call, or arrows at the
   wire). Each line is one arc of the net, and it diffs cleanly.
2. **A Network owns the Records only it touches.** Each is written before it is read
   in every firing, so it is scratch, never memory; one shared copy, as the original
   kept it in one register. Anything read outside the Network is an input or output. The other
   option, every scratch value declared at the top, changes a bundle's inputs and outputs at every
   split inside it, against the map's rule that a split keeps every contract.
   Tested on Doom (`P_ZMovement`'s float block, `P_AproxDistance`) and OoT (Player's
   file statics: `sSavedCurrentMask` is scratch, `sPrevFloorProperty` is state).
3. **One input or output, one field; never a whole Record.** The purest: the Network holds every
   wire, and a reader 1000 years on reads what touches what from the text alone,
   with no tool. Folding long wirings is the viewer's job.
4. **`slot` leaves every Network but the one that walks the slots.** A bundle gets
   `objects.x[slot]` already chosen, as the original's `mx1` pointers gave each
   routine "this object's x". A slot the game computes lives in a Record
   (`launch.slot`), and the Network wires the whole field beside it. `requires: slot < 2`
   moves to the walking Network. A `run` passes only wires.
5. **Whole field vs one slot:** the kind says it. `in table: word[N]` takes the field
   without `[slot]`; its index is another input.

## Found on the way, not this map's

- **Recursion.** Doom's `P_RecursiveSound` and OoT's `SkelAnime_DrawFlexLimb` keep
  values across a call to themselves. One copy of a Record, owned or not, cannot;
  that needs a copy per depth. Spacewar does not recurse.
- **Game state computed while drawing.** OoT's sword hit quads and `leftHandPos` come
  from the draw's matrix stack (`z_player_lib.c` `Player_PostLimbDrawGameplay`).
- **The spec calls `word` the PDP-1's.** It is the game's number: 18-bit ones'
  complement is a rule of Spacewar, stated exactly in DIGS. The spec rewrite says so.
