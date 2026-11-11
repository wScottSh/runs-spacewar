# Pilot split prototype (throwaway)

For "Hand-decompose a few Processors of the pilot" (#51). Arithmetic split into
stateless Processors with Ports, in a scratch copy, each variant compiled. Nothing here
is in `runs/`. `pilot_split.py` reruns every variant; `atoms.txt` holds the pieces the
Networks share.

| variant | split | Evaluator | image |
|---|---|---|---|
| `multiply_net` | `multiply` a Network: `magnitude` x2, `multiply_steps`, `copy` x2, `exclusive_or`, `negate_double`; owns `high`, `signs` | `check_multiply` 21453/21453 mpy and imp | MATCH |
| `arith_net` | also `divide` a Network: `overflows`, `magnitude`, `copy` x6, `negate_double`, `subtract`, `divide_steps`, `remainder_bit`, `negate` x2, `exclusive_or`, `fits`; owns `high` | `check_divide` 27224/27224 dvd (13799 overflow, 13425 fit), 27227/27227 idv | MATCH |
| `inertia_split`, `OWNED=1 DECL=drift` | `inertia` a Network: `sum`, `pass`, `drift`; owns `v` | | MATCH |
| `sqrt_net` | `square_root` a Network over a loop with `break` and two `continue`s: `square_root_start`, `increment` x2, `double`, `take_two_bits`, `copy` x2, `trial`, `negate`; owns `input_bits` (IO), `next` | `check_square_root` 65536/65536 | MATCH |
| `arith_net` with `sqrt_net` | multiply, divide and square root as Networks at once | | MATCH |
| `sine_copies` | the series' moves as one `copy`, 6 wirings | | MATCH |
| `sine_atoms` | also the coefficients through one `add`, read from a constant Record | | refused: `sine_constants.c1 has no data word` |
| `inertia_split`, `DECL=pieces` | `accumulate` + `drift`, no scratch: `drift` rereads the velocity | | 1 word longer a use (6 uses +6, 2 uses +2) |
| `inertia_split`, `DECL=network` | the bundle itself declared `[[inline]]` | | lift C: `undeclared name 'acceleration'` |

## What made it compile

A value one piece hands the next, which the original kept in AC or IO, is the Network's
owned scratch. runsc compiles it as a local of the subroutine, and pdp1cc keeps that
local in a register, through the rule runsc already had: a scalar Record none of whose
fields has a word lives in AC or IO. runsc had refused owned scratch, and the owned
Record's name (`multiply.owns`) held a dot, which runsc reads as Record.field. Removing
the refusal and naming it `multiply$owns` was the whole compiler change. No declaration
changed. Three more small changes followed for square root: a declaration names
scratch as it names a `let` (`io = ["input_bits"]`); scratch is declared once at the
top of the routine (the first build declared `word next` three times, shadowing it,
and still built the image); and a Network loop may `continue`, as the original jumps
back to `sq3` mid-body. The other shape, nesting the rest of the body under the
opposite guard, needed a new layout rule in runsc (the nested test jumping back to the
head) that no second program in the repo's sources shows, so it was dropped.

The text has to say what the original did. Two first drafts differed from the image,
and both were wiring mistakes, not compiler gaps. `magnitude` negated its out Port in
place, where the original negates in AC and stores once. `negate_double` negated `high`
after the sign test's xor had taken AC, where the original reloads the partial
product. Inertia's reload was the same kind of mistake: the new velocity is scratch.

Planted defects: square root's `if next > 0` made `>= 0` gives 29967 of 65536
differing; multiply's second `magnitude` wired to `entry` gives 1496 of 1653
calls differing; divide's remainder-sign guard flipped gives 7346 of 7727 differing in
the Evaluator, and the image differs at 00366 (`spi i` became `spi`).

## Still open

- **Constants have no wire.** Wires are fields; a scalar field nobody sets is not laid
  out as a literal. Pieces keep their constants for now (`square_root_start`,
  `overflows`).
- **The sine series and integer divide/multiply** are not split here.
- **A Network has no `return`.** square_root's loop ends the routine, so `break` ends it.
- **A bundle declared `[[inline]]` loses its register Ports.** Declaring a piece
  (`drift`) instead avoids it.

## Shared pieces

`magnitude` (multiply x2, divide), `negate_double` (multiply, divide), `copy` (sine,
multiply, divide, square_root), `negate` (divide, square_root), `exclusive_or`
(multiply, divide).
