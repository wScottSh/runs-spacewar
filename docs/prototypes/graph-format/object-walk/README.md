# The object walk as a threaded fold

Prototype for "Threading a Record several Processors write" (#57), part of #54.
The object table is written by collision and by each calc routine during the
walk. Here the walk is a set of bundles in the arc-list format (`../two-level/`).
Each step takes the table's current value and gives the next, so the order
of the collisions and the calc routines follows from the chain. The loader
generates the walk's RUNS source from these files. That source is what
`runs/` now holds, and runsc compiles it to the original program.

## The bundles

| file | what it is |
|---|---|
| `object_walk.net` | the walk: a fold of `object_step` over slots 0 .. 026, then `last_object(027)` |
| `object_step.net` | one slot: `active_object` when the slot is in use, else the table and the count go on as they are |
| `active_object.net` | count the object, fold `collide_pair` over the later slots when it can collide, then `calc`, then charge its time |
| `collide_pair.net` | `collision` on two entries when the later one can collide |
| `last_object.net` | slot 027: `calc` and its time, no collisions, no count |
| `calc.net` | the dispatch on the routine word: `torpedo` is a bundle; the other five are legacy routines |
| `torpedo.net` | the torpedo (tcr): 8 Processors with inputs and outputs, and `plot_torpedo` |
| `storage.toml` | the PDP-1 side: where the root's boundary and the torpedo's AC values live |

The Processors are the ones in `runs/`. This change gave nine of them inputs and
outputs in place of Record names: `collision`, `count_object`, `count_down`,
`explode_torpedo`, `warp_from_x`, `warp_from_y`, `torpedo_space_warpage`,
`inertia_x` and `inertia_y`. `collision` lost its three early returns (BlooP).
The image stayed identical at each step.

## What is new against two-level

- **A fold.** `each_slot: object_step(slot) for slot in 0 .. 026` runs the step
  bundle once a slot. Each inout of the step threads, so one step's out value
  is the next step's in value. The arcs wire the first in value and the last
  out value: `table -> each_slot.table` and `each_slot.table -> walked`. The
  count is fixed before the fold starts, as the BlooP rule requires.
- **A bundle with slots.** `network object_step(slot)` takes which slot, as
  today's `network torpedo(slot)` does. The slot is not an input.
- **A collection value.** A place may hold a whole table (`walked: objects`),
  and an arc end may name one entry of it (`table[slot].x`). An entry of the
  out value that nothing writes is the in value's.
- **Legacy routines.** A routine that still names its Records (`explosion`,
  `charge_time`, `plot_torpedo`) is wired with arcs that have no input or
  output: `table -> exploding` and `exploding -> table` state which values it
  reads and gives in their words.

Inside a bundle, an inout's name read is its in value and written is its out
value. A value read again after it is given goes through a `copy`, as in
multiply (`give_x`, `give_counter`). Every such copy compiles to nothing.

## How write-once values become the original's words

Every value in the graph is written once: 4 table values in `active_object`
(`table`, `collided`, `calculated`, and the out value), one a slot in the fold,
one a pair in the collision fold. On the PDP-1 they are one table. The rule:
**a fresh value takes its predecessor's word**. The two ends of an inout (a
Processor's, a bundle's, a fold's) share one word, and so do a copy's source and
target. `Storage` in `load.py` applies the rule. `hazards` then checks that it is
safe. On every branch, in the derived order, a value is never read after the next
value has taken its word. When the check passes, the predecessor is dead before
its word is reused, and the in-place program is the write-once program.

The rule costs the image nothing: no word is added, and the image is identical.
Had a value been needed after its successor, `Emit` would refuse (`in and out in
two words ... a fresh word costs`). That would cost one word and one copy.

## The order

Nothing in these files states the order. `schedule` works depth first from each
bundle's outputs, in the order the bundle declares them. The interleaving of
the original follows from the chain:

- `calc` reads `collided`, which the collision fold writes, so a slot's calc
  routine comes after its collisions.
- The fold threads the table, so slot k + 1's collisions read what slot k's calc
  routine gave. A torpedo that a ship launches into a later slot is counted,
  tested for collisions, and moved in the same frame.
- `charge_time` reads `calculated[slot].cycles`, the value after `calc`.

One choice is not data. `count_object` touches only the count, not the table.
It comes first because `active_object` declares `inout seen` before `inout table`.
With the two lines swapped, the count moves after `calc`, and the image
differs at 01451 (want 261737, got 261736). That is the one remaining place where a declaration's order decides
the image. It is the same tie-break the two-level loader uses, and here it
matters.

## Collisions as a phase of their own

`phases/` holds a variant. One fold runs every slot's collisions, then a second
fold runs every slot's calc routine. The same loader generates its source (two
`for` loops). runsc refuses it: `draw_outline` jumps through the ship's outline
word, and the declarations load that word in the walk that the variant split
in two. `phases/compare.py` runs both programs in the Evaluator on
check_frame's 300 frames. 24 frames differ, all in `frame.objects_seen`. A
torpedo launched into a later slot during the frame is not counted, because
the counting ran before the launch. No other Record and no plotted point
differ in those 300 frames. The ticket's figure (294 of 300) was not
reproduced by this variant.

## Results

`uv run -q python docs/prototypes/graph-format/object-walk/load.py`:

- The derived orders, the same source for 50 shuffles of every file, and the
  storage check: `no value is read after the next one takes its word`.
- `object_walk`, `calc` and `torpedo` in `runs/` are the generated source.
- runsc: identical to the original (`8744e9c9…`).

On `runs/` as generated: `check_calc_routines.py 1000` gives 1000 of 1000 for each
calc routine, the torpedo included. `check_frame.py 300` gives 300 of 300.
`check_all.sh` passes.

## Planted defect

In `torpedo.net`, `moved_x -> show` changed to `table[slot].x -> show`. The
graph then says the torpedo is drawn at its old x. The generated source does not
change (`run plot_torpedo(slot)` reads the word), so the image and SIMH would
not show the defect. The storage check does: `torpedo ('else',): show reads
table[slot].x, but objects.x[slot] holds moved_x`.

## What the gauge says

`tools/check_vision.py` in_place: 30 before and 30 after. `objects` still counts,
with the same fields. Two reasons:

- The source that runsc compiles writes the table in place, by the rule
  above. A Processor with an inout wired to `objects.counter[slot]` updates
  that word. The gauge now reads each wired copy of a Processor with inputs
  and outputs. Before that fix it read only the template, and it showed a false
  drop: counter went from 12 to 8 sets and routine from 13 to 10.
- `objects` has other writers outside the walk: `clear_tables`, `place_ships`,
  the spaceship's `place_torpedo`, `arm_torpedo`, `trigger`, `reload_tube`,
  `spaceship_in_star`, `take_torpedo_dx` and `take_torpedo_dy`, and hyperspace's
  `begin_breakout`, `end_breakout`, `jump`, `head_out`, `time_breakout`,
  `lost_in_hyperspace`, `enter_hyperspace`, `time_hyperspace` and `free_slot`.

names_records fell from 149 to 140 (the nine Processors). control_flow rose from
32 to 33: `object_walk` is a network of its own, split from `object_loop`.

## What a full conversion of the table needs

- The other five calc routines as bundles: `explosion` (its particle loop has a
  mid-body exit), `in_hyperspace`, `breakout`, and both spaceships. Each
  Processor they fire needs inputs and outputs in place of Record names.
- `plot_torpedo` and every Processor that emits to `display`: a Processor with
  inputs and outputs cannot name the stream today (`runs.check_template`). The
  display needs to be a value a Processor takes and gives, threaded like the
  table.
- `charge_time`: the declarations name it in `[walk] home_in`, and runsc
  resolves that name before it expands the copies of a Processor with inputs
  and outputs (`copies_of` covers `place` and `inline` only). With inputs and
  outputs, it fails: `walk.home_in 'charge_time' is no routine`. This needs
  a compiler rule, or one renamed value in `pdp1/main_loop.toml`.
- The writers outside the walk (`new_game`, the spaceship's launch): each is a
  step that takes the table and gives the next. A launch writes a later slot,
  so it gives a whole table, not an entry.
- The walk's own source still has `for` and `if` with no `else`. The graph has
  every `else` as a copy that compiles to nothing. Removing the gap needs runsc to
  compile the graph itself, not the generated source.
- `object_loop`'s planetarium, central star and spare time have no data link
  to the walk except through `display` and `pacing`. Threading those two
  values would derive their order as well.

## Files

- `*.net`: the bundles. `storage.toml`: the PDP-1 side.
- `load.py`: parses, checks, orders, checks storage, generates, and compiles.
  `--write` puts the generated source into `runs/`. `--dir` and `--into` run a
  variant.
- `phases/`: the separate-phase variant and `compare.py`.
