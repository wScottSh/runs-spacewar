# Order between independent transitions

Prototype for "Order between independent transitions" (#63), part of #54.
Nothing here is in `runs/` or `pdp1/`. One `tools/runsc.py` change, below.

When two transitions do not depend on each other, any order is the same game,
but only the original's order compiles to the original program. The arcs
prototype (`../two-level/`) broke such ties by the order of a Processor's
inputs, a PDP-1 fact in a Rules file. This directory measures how much freedom
the arithmetic's graphs leave, and replaces that tie-break with a rule that
reads nothing in a Rules file.

## The rule

The PDP-1 back end orders a Network's transitions so:

1. **Data.** A transition comes after the transitions that write what it
   reads and what its guard reads. Each branch of a test stays one block.
   (The wiring.)
2. **Storage.** No word is overwritten while its value has a read to come
   (`orders.hazards`: a value sharing a word is computed after its
   predecessor's last read). (Where values live on the PDP-1.)
3. **Registers.** runsc refuses an order that clobbers AC while it holds a
   value, or that sets a by-name argument anywhere but just before the run.
   (The back end itself.)
4. **Tests last.** Among the transitions that may go next, an unguarded one
   goes before a test's branch: work that does not depend on a test is done
   before it. (The graph's guards.)
5. **Arrival.** Then a transition that reads a value the call hands over
   earlier goes first: the jda entry word (`entry`), then IO (`io_param`),
   then the word after the call (`byname`); one that reads none of them goes
   after. (The routine's declaration in `pdp1/*.toml`, entries that exist.)

`rule.py` ranks the orders 1 and 2 allow by 4 and 5, transition by transition,
and keeps the first that runsc compiles (3). A transition's rank is the set of
places it reads and whether it has a guard. The order of a Processor's inputs,
of a network file's lines, and names play no part: names break the ties
left, and run with names backward the image is the same.

Kinds: 1 and 4 come from the graph. 2, 3 and 5 are PDP-1 back-end facts; 5
reads only existing declaration entries. No rule reads the original listing.
No declaration entry is added.

## How much freedom there is

`run.py` enumerates every order each graph allows, drops those with a storage
hazard, emits the stored source of each, and compiles it:

| graph | orders the graph allows | the stored words allow | distinct sources | runsc refuses | compile, differ | identical |
|---|---|---|---|---|---|---|
| multiply | 20 | 20 | 10 | 8 | 1 | 1 |
| integer multiply | 1 | 1 | 1 | 0 | 0 | 1 |
| divide | 15744 | 384 | 16 | 14 | 1 | 1 |
| integer divide | 1 | 1 | 1 | 0 | 0 | 1 |
| sine | 10 | 2 | 2 | 1 | 0 | 1 |
| cosine | 1 | 1 | 1 | 0 | 0 | 1 |

Data, storage and registers leave two choices in the whole arithmetic:

- **multiply**: `|entry|` before `|factor|`, or after. Both compile, to the
  same number of words. After differs at 00172 (want 260200, got 260173).
  Fact 5 decides: `magnitude_of_entry` reads the entry word, `magnitude_of_factor`
  the word after the call.
- **divide**: the skip return (`division_fits`, `idx dv1`) before or after the
  quotient's sign (`xct dv1; xor dvd`). Before differs at 00371 (want 100317,
  got 440317). Fact 5 decides: `sign_of_quotient` reads the divisor (by name),
  `division_fits` reads nothing.

Divide's other independent pair, `|divisor|` and `|dividend|`, is decided by the
registers: the dividend first is refused (`AC local dividend_high was
clobbered`). Today's rule picks the dividend first, because `subtract` lists
`a` (the dividend) before `b`.

The object walk (`../object-walk/`) has a third choice: `count_object` before
or after the collision test in `active_object`. Fact 4 decides it.

## Proof: every input order reversed

`run.py` runs each graph twice: with the files as written, and with the `in`,
`inout` and `out` lines of every Processor file and bundle file reversed (the
reversed Processor files are what runsc compiles). Each time with names
breaking ties forward and backward, and with 5 shuffles of the network file.

| graph | today's rule, as written | today's rule, reversed | this rule, all eight runs |
|---|---|---|---|
| multiply | identical | differs at 00172 | identical |
| integer multiply | identical | identical | identical |
| divide | runsc refuses | storage hazard | identical |
| integer divide | identical | identical | identical |
| sine | identical | runsc refuses (`run multiply without setting multiply_call.factor just before`) | identical |
| cosine | identical | identical | identical |

`walk.py` does the same for the object walk, whose loader now uses the rule:
every network file's port lines reversed (so `inout seen` and `inout table`
swap), names forward and backward. Identical all four times. Before, the swap
alone gave a difference at 01451.

Each fact earns its place (planted defects):

- Without fact 5 (`drop.py`), names backward: multiply picks `|factor|` first
  and differs at 00172; divide puts the skip return before the quotient's sign
  and differs at 00371. Fact 4 decides nothing in the arithmetic.
- Without fact 4 (`walk.py`), the walk with names backward puts the count after
  the collision test: differs at 01451 (want 261737, got 261736).

The Evaluator agrees with SIMH on both generated sources (every place its own
field, and places sharing PDP-1 words) of each picked order: multiply and
integer multiply 3453 of 3453 calls, divide 9224 of 9224, integer divide 9227
of 9227, sine and cosine 2046 of 2046 sampled words (`run.py --n 2000`).

## The graphs

- `../two-level/multiply.net`, `../two-level/integer_multiply.net`: as #56 left them.
- `divide.net`: a bundle of 16 transitions. The two sign fixes and the
  dividend's magnitude are Processors with an `if` in the body
  (`magnitude_double`, `sign_like`, `sign_like_in_place`); the graph has one
  test, whether the quotient fits. The cleared IO before the halving is a
  place written by `clear`, so the storage check sees it.
- `integer_divide.net`: `shift_right_17`, then `divide` as one transition.
- `sine.net`: a bundle; `multiply` six times as transitions, the constants as
  Processors with no inputs (`two_over_pi`, `sine_c7`), the saturation as a test.
- `cosine.net`: `add_half_pi`, then `sine` as one transition.
- Square root is not converted: its loop exits mid-body, which another ticket owns.

`storage.toml` holds 10 prototype storage entries (multiply 2, divide 5, sine 3):
which word a work value shares. They are storage, not order, and stay outside
`pdp1/`.

## What it took

- **runsc** (`tools/runsc.py`): a routine's AC result set inside a branch is
  declared at the top of the C function. Before, sine's graph, whose result is
  set in both arms of the saturation test, compiled to C that declared the
  result inside each arm. Today's sine sets it inside an arm too and returns
  there; it compiles to the same image either way.
- **The generator** (`arith.emit`): an else that only writes the declared skip
  field (`skips`) is written before the if, since runsc compiles an empty else
  to a jump.
- **Shapes chosen for runsc**: the final sign of divide's quotient sets its
  output and then negates it (`sign_like_in_place`). With a local (`sign_like`),
  runsc's return of a last-statement result drops the second result (IO). The
  shift in integer divide names its IO local `low`, the name runsc keeps in IO.

## Found on the way

runsc compiled one divide order to a wrong program without refusing it. With
the halving's cleared IO as a Processor local (`let low = 0`) and `halve`
placed before the quotient's store, it emitted `cli; rcr 1s; dio idv`: IO, which
held the quotient, was cleared before it was stored. The Evaluator, which has
no registers, cannot see it. The prototype makes the cleared IO a place, so the
storage check refuses that order; runsc's own check of IO stays open.

## Run it

```
uv run -q python docs/prototypes/graph-format/order/run.py [routine ...] [--n N]
uv run -q python docs/prototypes/graph-format/order/drop.py
uv run -q python docs/prototypes/graph-format/order/walk.py
```

Needs `build/oracle.lst`, `build/oracle.rim` and `build/pdp1`. `run.py` compiles
each distinct source once per file variant.
