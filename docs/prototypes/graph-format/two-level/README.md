# Two levels: integer multiply uses multiply as one transition

Prototype for "How a Network is written as a literal graph" (#56). It answers the
user's correction: the higher network file wires only whole bundles, and each
bundle has its own network file. A bundle is used from outside exactly as a
Processor is (`../../../../../.github/CONTEXT.md` 229-236, Sub-Network). It has inputs and outputs at its
boundary, and its own Records are invisible outside.

Format: the arc list (`../arcs/`). Nothing here is in `runs/`, `pdp1/` or `tools/`.

## The caller

integer multiply (`imp`) is the smallest real caller of multiply in `runs/`. It
runs multiply once. Today it is three steps: `integer_multiply_factors` swaps
the two factors, `run multiply`, and `integer_multiply_product` rotates the low
half's sign to bit 0. As a graph, the swap is two crossed arcs and needs no
Processor. The rotate is one Processor (`processors/rotate_right.runs-prim`).
The other callers are `sine` and `cosine`, which run multiply six times among
seven Processors.

## multiply's bundle file: `multiply.net`

```
# multiply (mpy), a bundle. Its inputs and outputs are declared as a
# Processor's are; inside, an arc names one by itself, with no Record.
# multiply_work is multiply's own: nothing outside names it.

network multiply
  in entry: word
  in factor: word
  out partial: word
  out low: word

places
  multiply_work.entry_magnitude
  multiply_work.factor_magnitude
  multiply_work.high
  multiply_work.low
  multiply_work.saved_high
  multiply_work.signs
  multiply_work.reloaded_high
  multiply_work.negated_high

transitions
  magnitude_of_entry: magnitude
  magnitude_of_factor: magnitude
  steps: multiply_steps
  save_high: copy
  sign_of_product: exclusive_or
  reload_high: copy
  negate: negate_double
  give_negated_high: copy
  give_high: copy
  give_low: copy

arcs
  entry -> magnitude_of_entry.value
  magnitude_of_entry.magnitude -> multiply_work.entry_magnitude
  factor -> magnitude_of_factor.value
  magnitude_of_factor.magnitude -> multiply_work.factor_magnitude
  multiply_work.entry_magnitude -> steps.low
  multiply_work.factor_magnitude -> steps.multiplicand
  steps.high -> multiply_work.high
  steps.low -> multiply_work.low
  multiply_work.high -> save_high.source
  save_high.target -> multiply_work.saved_high
  factor -> sign_of_product.a
  entry -> sign_of_product.b
  sign_of_product.result -> multiply_work.signs
  multiply_work.signs -> reload_high when < 0
  multiply_work.saved_high -> reload_high.source
  reload_high.target -> multiply_work.reloaded_high
  multiply_work.reloaded_high -> negate.high
  multiply_work.low -> negate.low
  negate.high -> multiply_work.negated_high
  negate.low -> low
  multiply_work.negated_high -> give_negated_high.source
  give_negated_high.target -> partial
  multiply_work.signs -> give_high when else
  multiply_work.saved_high -> give_high.source
  give_high.target -> partial
  multiply_work.signs -> give_low when else
  multiply_work.low -> give_low.source
  give_low.target -> low
```

It is `../arcs/multiply.net` with the four `multiply_call` places replaced by
four `in` and `out` lines, and `multiply_call.x` written `x` in 8 arcs. It
names no caller's Record. Both files have 54 lines without comments or blanks.

## The parent network file: `integer_multiply.net`

```
# integer multiply (imp). multiply is one transition, wired as a Processor is.
# imp keeps the low half: it drops the high half and rotates the low half's sign to bit 0.

network integer_multiply

places
  integer_multiply_call.entry
  integer_multiply_call.factor
  integer_multiply_call.product
  integer_multiply_work.high
  integer_multiply_work.low

transitions
  multiply: multiply
  sign_to_bit_0: rotate_right

arcs
  integer_multiply_call.factor -> multiply.entry
  integer_multiply_call.entry -> multiply.factor
  multiply.partial -> integer_multiply_work.high
  multiply.low -> integer_multiply_work.low
  integer_multiply_work.low -> sign_to_bit_0.value
  sign_to_bit_0.rotated -> integer_multiply_call.product
```

## New line forms, against the one-level arcs file

| line form | where | why it could not be avoided |
|---|---|---|
| `  in <name>: <type>` and `  out <name>: <type>` under `network` | bundle file | The boundary must be stated somewhere, and this is the form a Processor file already uses. The loader reads a Processor's and a bundle's inputs and outputs with one function (`signature`). It could be avoided: an arc end with no Record could be read as an input when it feeds a transition and as an output when a transition writes it. That loses the type (a bare name has no Record to carry one), and a misspelled name would become a new input with no error. The order of the `in` lines does not decide the image: swapped, the program is still identical to the original. |
| an arc end that is one name: `entry -> magnitude_of_entry.value`, `give_low.target -> low` | bundle file | Inside the bundle, an input or output is a place that belongs to no Record. Naming it `multiply.entry` would invent a Record called `multiply`, and `x.y` already means a transition's input or output when `x` is a transition. |

The parent file has no new line form. `multiply: multiply` is the same line as
`sign_to_bit_0: rotate_right`. The arcs into and out of `multiply` are the same
form as the arcs into and out of `sign_to_bit_0`.

## The use site is identical

The parent cannot tell a bundle from a Processor. The loader resolves the name
on the right of a `transitions` line to `processors/<name>.runs-prim` or to
`<name>.net` beside the parent, and reads `in` and `out` lines from either file
the same way:

```
multiply: multiply.net, inputs ['entry', 'factor'], outputs ['partial', 'low']
rotate_right: rotate_right.runs-prim, inputs ['value'], outputs ['rotated']
```

## What the parent sees of multiply

Two inputs (`entry`, `factor`) and two outputs (`partial`, `low`), each a word.
It does not see `multiply_work`, the ten transitions, the guard, or the two
branches. The parent's order is derived from its own wiring alone:
`multiply, sign_to_bit_0`.

The parent wires `multiply.partial` to `integer_multiply_work.high`, which
nothing reads. imp drops the high half, but the check requires every output to
be wired once.

## Where the generated source differs between the two

The network files agree. The RUNS source the loader generates for today's
compiler does not, because today a `run` passes no values to a Network. So for
a bundle transition the loader copies each input into the bundle's word before
`run multiply`. It reads each output from the bundle's word afterward. The
stored version, which runsc compiles:

```
network integer_multiply
  writes: integer_multiply_call, multiply_call
  run copy
    source: integer_multiply_call.factor
    target: multiply_call.entry
  run copy
    source: integer_multiply_call.entry
    target: multiply_call.factor
  run multiply
  run rotate_right
    value: multiply_call.low
    rotated: integer_multiply_call.product
```

Where multiply's inputs and outputs live on the PDP-1 is not in either network
file. The loader puts them in the fields of `multiply_call`, named
`<bundle>_call` after the bundle, as `runs/` does for every jda routine
(`square_root_call`, `sine_call`, `integer_multiply_call`). It checks that the
Record's fields are the bundle's inputs and outputs. That is a naming rule in
the loader. It adds no entry to `storage.toml` or `pdp1/`. Once renamed this way,
multiply's graph is the same as `../arcs/multiply.net`'s: the loader prints
`True` for that comparison.

## Results

`uv run -q python docs/prototypes/graph-format/two-level/load.py`:

- The Evaluator against SIMH, both sources (every place its own field, and
  places sharing PDP-1 words): multiply 21453 of 21453 calls agree, and
  integer_multiply 21453 of 21453 calls agree.
- runsc compiles the stored source to the original program, byte for byte:
  sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
- Each level's order is the same for 50 shuffles of its file.

## Planted defects

Each defect is a two-line edit of `integer_multiply.net`, loaded with
`load.py 2000 <copy>/integer_multiply.net` and the bundle file copied beside it.

1. **Crossed output wires**: `multiply.partial -> integer_multiply_work.low` and
   `multiply.low -> integer_multiply_work.high`. Predicted: imp rotates the
   high half, so its AC is wrong for nearly every call, and multiply's own
   words stay right. Seen: integer_multiply 3304 of 3453 calls differ, every
   one on AC (`integer_multiply(000001, 000001): AC simh 000001 runs 000000`).
   multiply's own check: 3453 of 3453 agree. No call differs on `mpy` or `mp2`.
   runsc refuses the source before any image is built: `integer_multiply: no
   statement boundary after the last by-name read where AC is dead and every
   path to a return passes`.
2. **Uncrossed input wires**: `integer_multiply_call.factor -> multiply.factor`
   and `integer_multiply_call.entry -> multiply.entry`. Predicted: the product
   is the same (multiplication commutes), but multiply's `entry` word (`mpy`)
   holds the other factor. Seen: no call differs on AC. 3410 of 3453 calls
   differ on `mpy` (`integer_multiply(000000, 000001): mpy simh 000001 runs
   000000`). The 43 that agree are the 43 calls whose two factors are the same word. runsc refuses the source:
   `operand Var(name='factor', storage=ByName(name='factor')) must be a memory
   operand or a constant`.

I predicted that each defect would build an image that differs from the
original. It did not: runsc rejects both sources before assembling, so there is
no first differing address to report.

## Limits

- The parent is not itself a bundle. Its places are `integer_multiply_call`
  fields, imp's own jda words, which stand in for the caller's Record. When
  imp's callers (`spaceship.runs-prim`) are converted, `integer_multiply.net`
  gets `in` and `out` lines and bare names, the same two forms as multiply.
- The parent's generator (`emit_parent`) handles no guard and no `inout` in a
  level that runs a bundle. imp needs neither.
- `load.py` builds one bundle, multiply, and splices imp in place of today's
  `integer_multiply`. It reuses `graph.py` and `../arcs/load.py` and changes
  neither.

## Files

- `multiply.net`: multiply's bundle file.
- `integer_multiply.net`: the parent.
- `processors/rotate_right.runs-prim`: imp's `rir 1s`, the one Processor imp adds.
- `records/integer_multiply_call.runs`: imp's words, moved out of `runs/spacewar.runs`
  in the scratch copy.
- `records/integer_multiply_work.runs`: the two values imp gets from multiply.
  Only the first source (every place its own field) uses it.
- `load.py`: resolves, checks, orders, generates, splices, runs the Evaluator
  and runsc. The SIMH cases need `build/oracle.lst`, `build/oracle.rim` and
  `build/pdp1`.
