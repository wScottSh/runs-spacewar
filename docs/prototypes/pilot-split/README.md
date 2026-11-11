# Pilot split prototype (throwaway)

For "Hand-decompose a few Processors of the pilot" (#51). Three arithmetic pieces
split into stateless Processors with Ports, in a scratch copy, each compiled. Nothing
here is in `runs/`. `pilot_split.py` reruns every variant.

| variant | split | Evaluator | image |
|---|---|---|---|
| `inertia` | today's `inertia_x/y` as one `inertia` with Ports | loads | MATCH |
| `inertia_split`, `DECL=network` | `inertia` a Network bundle of `accumulate` + `drift`, declared `[[inline]]` | loads | lift C fails: `undeclared name 'acceleration'` |
| `inertia_split`, `DECL=pieces` | same, the two pieces declared `[[inline]]` | loads | differs: 6 words longer |
| `sine_copies` | the series' moves as one `copy` atom, 6 wirings | loads | MATCH |
| `sine_atoms` | also the coefficients through one `add` atom, read from a constant Record | loads | refused: `sine_constants.c1 has no data word` |
| `multiply_net` | `multiply` a Network: `magnitude` x2, `multiply_steps`, `copy`, `exclusive_or`, `negate_double`; owns `high`, `signs` | `check_multiply`: 21453/21453 mpy, 21453/21453 imp | refused: `owned scratch not compiled yet` |

## What each result says

1. **One-statement atoms compile to the original where no value crosses the cut in a
   register.** `sine_copies`: six `copy` wirings, no declaration change, MATCH.
2. **A value the original keeps in AC across a cut costs a reload.** `drift` reads the
   velocity `accumulate` just stored; the original's `diff` keeps it in AC. Measured:
   splitting all 6 uses adds 6 words, splitting only spaceship's 2 adds 2 (the
   constant pool moves by that much). Needed: a load-after-store rule (`dac x` then
   `lac x` drops the `lac`), an idiom of every hand-written PDP-1 program.
3. **A bundle declared `[[inline]]` loses its register Ports.** With `inertia` a
   Network, runsc inlines it as `void(void)` and the AC input never arrives.
4. **A constant has no wire.** Wires are fields, so a coefficient has to be a field;
   runsc lays out only a collection field nobody sets as constants, not a scalar.
   Needed: a scalar field no routine sets compiles to a literal (`add (121312`).
5. **Handed values in a split Processor are owned scratch, which runsc refuses.** The
   multiply Network is right (the Evaluator matches SIMH; wiring `magnitude`'s second
   run to `entry` gives 1496 of 1653 calls differing), but `high` and `signs` were AC.
   This is the map's fog item "lowering such a Record to the register the original
   kept it in".

## Shared pieces found

`magnitude` (multiply x2, divide's divisor), `negate_double` (multiply, divide),
`copy` (sine x6, multiply x1-2), `exclusive_or` (multiply, divide's sign test). Divide
was not split here; its uses move in the sweep.
