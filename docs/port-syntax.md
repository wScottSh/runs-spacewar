# Syntax for Ports and their wiring

Decided with the user, 2026-11-11, in "Syntax for Ports and their wiring in the RUNS
text" (#52). The spec text and a runnable example land with "Ports in the Evaluator
and runsc" (#53), when the Evaluator reads this syntax.

## The syntax

A Port is a header line, `direction name: kind`, the same on a Processor and on a
Network. It replaces `reads:`/`writes:`. A `run` wires one Port per indented line.
A same-name wire (`velocity: velocity`) may be left out.

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
  owns: acceleration                                        # scratch: only drift touches it
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

How `owns:` declares the Record's fields and kind is left to #53.

## The rules

1. **Header lines, one wire per line** (over parens like a call, or arrows at the
   wire). Each line is one arc of the net, and it diffs cleanly.
2. **A Network owns the Records only it touches.** Each is written before it is read
   in every firing, so it is scratch, never memory; one shared copy, as the original
   kept it in one register. Anything read outside the Network is a Port. The other
   option, every scratch value declared at the top, changes a bundle's Ports at every
   split inside it, against the map's rule that a split keeps every contract.
   Tested on Doom (`P_ZMovement`'s float block, `P_AproxDistance`) and OoT (Player's
   file statics: `sSavedCurrentMask` is scratch, `sPrevFloorProperty` is state).
3. **One Port, one field; never a whole Record.** The purest: the Network holds every
   wire, and a reader 1000 years on reads what touches what from the text alone,
   with no tool. Folding long wirings is the viewer's job.
4. **`slot` leaves every Network but the one that walks the slots.** A bundle gets
   `objects.x[slot]` already chosen, as the original's `mx1` pointers gave each
   routine "this object's x". A slot the game computes lives in a Record
   (`launch.slot`), and the Network wires the whole field beside it. `requires: slot < 2`
   moves to the walking Network. A `run` passes only wires.
5. **Whole field vs one slot:** the kind says it. `in table: word[N]` takes the field
   without `[slot]`; its index is another Port.

## Found on the way, not this map's

- **Recursion.** Doom's `P_RecursiveSound` and OoT's `SkelAnime_DrawFlexLimb` keep
  values across a call to themselves. One copy of a Record, owned or not, cannot;
  that needs a copy per depth. Spacewar does not recurse.
- **Game state computed while drawing.** OoT's sword hit quads and `leftHandPos` come
  from the draw's matrix stack (`z_player_lib.c` `Player_PostLimbDrawGameplay`).
- **The spec calls `word` the PDP-1's.** It is the game's number: 18-bit ones'
  complement is a rule of Spacewar, stated exactly in DIGS. The spec rewrite says so.
