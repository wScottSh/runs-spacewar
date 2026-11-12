# How a Network is written as a literal graph: three formats for multiply

> **Moved to the real source (#62).** The arc-list loader is `tools/graph.py`,
> read by `runs.load`; the order rule and the storage rule are the PDP-1 back
> end's (`lower_for_pdp1` in `tools/runsc.py`), with no storage entries. The
> arithmetic's network, Processor and Record files are in `runs/arithmetic/`.
> The code and files this page runs are deleted; its tables and findings stand
> as the record of the prototype.

Prototype for "How a Network is written as a literal graph" (#56), part of "Write
RUNS as the vision's literal graph" (#54). Nothing here is in `runs/`, `pdp1/` or
`tools/`.

multiply (`mpy`) is written three ways. The Processor files and Record files are
the same for all three. Only the network file differs:

| | `arcs/multiply.net` | `blocks/multiply.net` | `dot/multiply.dot` |
|---|---|---|---|
| shape | places, transitions, then one arc a line | places, then one block per transition holding its wires | Graphviz DOT: circles, boxes, labeled edges |
| lines (without comments or blanks) | 54 | 51 | 46 |
| a guard is | `multiply_work.signs -> reload_high when < 0` | `when multiply_work.signs < 0` inside the block | a dashed edge labeled `< 0` |
| reads easily | what touches a place (grep the place) | what one transition takes and gives | the picture, once drawn |
| reads poorly | one transition's wiring (scattered over arcs) | what touches a place (scattered over blocks) | the file itself: quotes, brackets, `label=` on every arc |
| loader | `arcs/load.py`, 42 lines | `blocks/load.py`, 36 lines | `dot/load.py`, 50 lines |
| Evaluator, 21453 SIMH cases | 21453 match | 21453 match | 21453 match |
| image | identical to the original (`8744e9c9…`) | identical | identical |

The three loaders build the same graph: their output, with both generated sources,
is the same byte for byte.

## The same three transitions in each format

`arcs/multiply.net`:

```
transitions
  steps: multiply_steps
  reload_high: copy
  give_high: copy
arcs
  multiply_work.entry_magnitude -> steps.low
  multiply_work.factor_magnitude -> steps.multiplicand
  steps.high -> multiply_work.high
  steps.low -> multiply_work.low
  multiply_work.signs -> reload_high when < 0
  multiply_work.saved_high -> reload_high.source
  reload_high.target -> multiply_work.reloaded_high
  multiply_work.signs -> give_high when else
  multiply_work.saved_high -> give_high.source
  give_high.target -> multiply_call.partial
```

`blocks/multiply.net`:

```
  transition steps: multiply_steps
    low <- multiply_work.entry_magnitude
    multiplicand <- multiply_work.factor_magnitude
    high -> multiply_work.high
    low -> multiply_work.low

  transition reload_high: copy
    when multiply_work.signs < 0
    source <- multiply_work.saved_high
    target -> multiply_work.reloaded_high

  transition give_high: copy
    when multiply_work.signs else
    source <- multiply_work.saved_high
    target -> multiply_call.partial
```

`dot/multiply.dot`:

```
  steps [label=multiply_steps]
  reload_high [label=copy]
  give_high [label=copy]
  "multiply_work.entry_magnitude" -> steps [label=low]
  "multiply_work.factor_magnitude" -> steps [label=multiplicand]
  steps -> "multiply_work.high" [label=high]
  steps -> "multiply_work.low" [label=low]
  "multiply_work.signs" -> reload_high [label="< 0", style=dashed]
  "multiply_work.saved_high" -> reload_high [label=source]
  reload_high -> "multiply_work.reloaded_high" [label=target]
  "multiply_work.signs" -> give_high [label=else, style=dashed]
  "multiply_work.saved_high" -> give_high [label=source]
  give_high -> "multiply_call.partial" [label=target]
```

`dot -Tsvg dot/multiply.dot` should draw the net, but it was not drawn here
because Graphviz is not installed on this machine.

## The files every format shares

- `processors/`: one Processor in each file (`copy`, `magnitude`, `exclusive_or`,
  `multiply_steps`, `negate_double`), with inputs and outputs and no Record names.
  These are the bodies of `docs/prototypes/pilot-split/atoms.txt`.
- `records/multiply_call.runs`: what a caller hands multiply and gets back
  (`entry`, `factor`, `partial`, `low`). It replaces the Record in `runs/spacewar.runs`.
- `records/multiply_work.runs`: every value multiply computes along the way, one
  field for each, so that each is written once.
- `storage.toml`: the PDP-1 side. It has 2 entries: the two values the original keeps
  in `mp2` (`|factor|`, then the high half).
- `graph.py`: what the loaders share. It checks the graph, derives the order,
  generates today's RUNS source, and verifies it.

## What the network file states and what is derived

Stated: the places, the transitions (each with its Processor), and the arcs.
Each arc runs from a field to a Processor input, or from a Processor output to a
field. A guard arc runs from a field to a transition.

Derived, the same in all three formats:

- **The order.** Each place is written once, so the order follows from what
  each transition reads. `graph.schedule` walks back from multiply's outputs. A
  transition comes after the transitions that write its inputs, taken in the order
  its Processor lists them, and then after the transition that writes its guard's
  place. The network file's order plays no part: 50 shuffles of places,
  transitions and arcs give the same order.
- **The branches.** Only the first transition of a branch carries a guard
  (`reload_high`, `give_high`, `give_low`). `negate` and `give_negated_high` have
  no guard arc. They read values that only `reload_high`'s branch writes, so they
  fire only on that branch. A Petri net handles this with no extra syntax.
- **The checks.** Every input and output is wired once. Every place is a Record
  field. A place has two writers only on two branches of one test. Each test has
  its `else` (CONTEXT.md 354-356).
- **Storage, except for the 2 stated entries.** A value an `inout` replaces
  shares its word with the new value (`negate_double`'s `low`, `multiply_steps`'s
  `low`). Every other work value is register scratch owned by the Network, so
  `runsc` keeps it in AC or IO. A `copy` whose source and target share a word
  generates nothing. That is why the else branch, two copies, compiles to no code,
  as the original's `sma; jmp mp3` skips straight to the return.

Each loader generates two sources. In the first, every place is its own field;
the Evaluator runs it, and it shows the graph means multiply without any shared
word. In the second, places share the original's words; the Evaluator runs it
and `runsc` compiles it. Both agree with SIMH on 21453 of 21453 calls.

## What it makes hard

- **The order among independent transitions decides the image.** Any
  order is the same game, but only one is the original's code. Here the
  tiebreak is each Processor's input order. If `multiply_steps` listed
  `multiplicand` before `low`, the Evaluator would still match 1653 of 1653 calls,
  but the image would differ at 00172 (want 260200, got 260173). The network file
  states no order, but the Processor files' input order now carries one. A
  second tiebreak: the guard's writer (`sign_of_product`) comes after the
  data inputs.
- **Storage is stated, not derived.** `storage.toml` holds 2 entries.
  Moved into `pdp1/`, they would grow the declarations by 2, which only the user can approve.
  Deriving them would need a rule a second PDP-1 program also uses.
- **The 1962 register traffic is visible in the graph.** `save_high`,
  `reload_high` and the `give_*` copies are the original's `dac mp2` and `lac
  mp2`. They are there because the image needs them. A graph without them would need
  `runsc` to insert the moves.
- **The else branch is all copies.** Write-once means the result on the
  positive path is a fresh value too, so `give_high` and `give_low` exist only to
  satisfy the partition. They compile to nothing.
- **Format by format.** In `arcs`, `x.y -> a.b` is read by checking whether `x`
  is a transition name. A Record and a transition with the same name would be
  ambiguous. In `blocks`, the guard is written inside the transition, though
  in the vision it belongs on an arc. In `dot`, a drawing attribute
  (`style=dashed`) marks a guard, and a node is a place or a transition by the
  `node [shape=...]` default above it. That is the one place where a statement's
  position matters (it is not execution order).

None of the three needed the order written down, so none is disqualified.

## The loop

`multiply_steps` holds the loop in its body (`for step in 1 .. 021`), so no network
file has a loop. The original has no loop: `repeat 21, mus mp2` is 17 `mus`
instructions in the image. `loop/unroll.py` writes multiply with the 17 steps as
17 transitions of a one-`mus` Processor (`loop/multiply_step.runs-prim`), after a
`clear`, in the arc-list format. The chain of values
(`high_0 .. high_16`, `low_1 .. low_16`) derives the order. It needs no new syntax
and compiles to the original image, with 21453 of 21453 calls in both sources. The cost: the network
file grows from 54 to 186 lines (18 transitions, 86 arcs), and a Record of 32 fields
(`loop/multiply_steps_work.runs`) holds one value per step.

What each format needs for it:

- **arcs**: 5 arcs a step, one line each. Nothing new.
- **blocks**: one 5-line block a step. Nothing new.
- **dot**: 5 edges a step. Nothing new. Drawn, it is a long chain.
- All three: without new syntax, a count (17) can be stated only by writing the
  steps out. Stating it any other way (a repeat on a transition, or a Network that
  folds) is new syntax and belongs to the loop ticket. A loop with a data-dependent
  exit (square root) cannot be unrolled this way.

## Two levels

`two-level/` writes multiply as a bundle with its own network file, and a parent,
integer multiply (`imp`), that uses `multiply` as one transition in the arcs format.
The parent's use of `multiply` is the same line form as its use of a Processor. The
bundle file adds two line forms: `in` and `out` lines, as a Processor file has, and
an arc end that names one of those by itself. The Evaluator agrees with SIMH on
21453 of 21453 calls for both routines. The image is identical to the original. See
`two-level/README.md`.

## Run it

```
uv run -q python docs/prototypes/graph-format/arcs/load.py
uv run -q python docs/prototypes/graph-format/blocks/load.py
uv run -q python docs/prototypes/graph-format/dot/load.py
uv run -q python docs/prototypes/graph-format/loop/unroll.py
```

Each loader prints the derived order, both generated sources, the Evaluator's
count against SIMH, and runsc's image hash. The SIMH cases need `build/oracle.lst`,
`build/oracle.rim` and `build/pdp1`.
A planted defect (the guard `< 0` made `> 0` in `arcs/multiply.net`) gives 3410 of
3453 calls differing, and the image differs at 00231 (want 640400, got 650500).
