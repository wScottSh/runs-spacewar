# Which forms of today's RUNS can bind Records to a Processor

Issue #47 (part of #45). The question: which forms do `tools/runs.py` (the evaluator) and `tools/runsc.py` (the compiler) already accept, unchanged, that let a Network decide what a Processor acts on? Read from the code at `e7fa044`. Every claim cites the line that enforces it. Each "experiment" was compiled from a scratch copy of `runs/` with `RUNS_SOURCE=<copy> uv run -q python tools/runsc.py`. The real tree still prints `MATCH 8744e9c9…`.

## Short answer

- **A Network can bind slots, never Records or fields.** A `run` argument is an expression, but the evaluator lets a parameter stand only for a slot: an index, a `requires:`, a loop bound, or an argument passed on to another routine used the same way (`label_only`, runs.py:1228-1256). Any other use is an impurity (runs.py:1201-1205), and `runs.check` now refuses every impurity (runs.py:1926 → 1300).
- **Every Processor names its Records.** A field is read or written only as `<record name>.<field>`, and the name must be a Record (runs.py:1362-1366 statically, 822-829 at run time). A Record name on its own is no value (runs.py:1391). All 149 Processors in `runs/` name at least one Record, and 59 of them name no game Record.
- **No existing form lets two call sites hand different Records, or different fields, to one Processor body.** The nearest form is a **handoff or call Record**. The shared body reads and writes only its own interface Record. A small adapter Processor at each call site copies that site's Record in or out. Examples: `torpedo_space_warpage`, `inertia_x`/`inertia_y`, `integer_divide`, `multiply`. The shared body still names a game Record, its own call Record, but no Record that belongs to a caller.
- **The compiler is narrower than the evaluator in two places.** A routine bound in `pdp1/*.toml` may be run only with its caller's own parameter names (runsc.py:1738-1743). A slot held in a Record and passed as an argument breaks cursor derivation (experiment G).

## The forms

| # | Form | Evaluator accepts | Compiler accepts | Example in `runs/` | Binds | Processor names no game Record of its own? |
|---|---|---|---|---|---|---|
| 1 | Slot parameter into a collection | runs.py:421-433 (parse), 687 (bind), 1494-1499 (arity), 1228-1256 (label only) | inlined: runsc.py:1763 `substitute`; bound: 1738-1743 (same names only); cursors: 806-864 | `run collision(slot, other)` frame.runs:72; `run calc(slot)` and every `(slot)` Processor | which slot of a Record the body names | No. The body names the collection (`objects`, `ship_flight`). |
| 2 | Constant argument | same as 1; constant slot bound-checked at runs.py:1378-1380 | inlined only (runsc.py:1763); a table of constants folds per copy, runsc.py:143-163 with runs.py:1550-1580 | `run show_magnitude(0..3)` heavens.runs:33-36; `run torpedoes_left(0/1)` frame.runs:35,39; `run calc(027)` frame.runs:76 | which slot, fixed at the call site; through a constant table, a per-site constant | No, same as 1 |
| 3 | Slot held in a Record (`launch.slot`) | any number expression indexes (runs.py:826-828, 1378-1380) | `slot_cursors` derived from the text, runsc.py:852-864 | `objects.routine[launch.slot]` spaceship.runs:121, spaceship.runs-prim:332-340 | which slot, chosen at run time by a Processor that writes the holder | No: the body names the holder too |
| 4 | Handoff / call Record | ordinary Record reads/writes (Scope.check runs.py:1035-1044) | for bound JDA/JSP routines the call Record's fields are the call's arguments, set "just before": runsc.py:1923-1954, `Bound.params` 431-454 | `handoff` (spacewar.runs:403-430), `*_call` Records; `run warp_from_x(slot)` / `run torpedo_space_warpage` objects.runs:37-42 | which values a shared body sees, by which adapter the Network runs before it | The shared body names only its call Record (`handoff`, `multiply_call`). Adapters name both sides. |
| 5 | `match` dispatch on an enum field | runs.py:755-761 (run time), 1502-1508 (all arms, one enum) | jump through the word, each arm passes the scrutinee's slot: runsc.py:1817-1837 | `network calc(slot)` frame.runs:83-91 | which Processor or Network runs, not what it acts on | n/a |
| 6 | Sub-Network contract `reads:`/`writes:` | checked only: runs.py:1303-1348 | not read by codegen; no Network's `reads`/`writes` is consulted in runsc.py | `control_word`, `sine`, `cosine`, `integer_multiply`, `integer_divide`, the three top Networks | nothing: it declares which Records cross, it does not rename them | n/a: Networks hold no state anyway |
| 7 | `for` loop variable | runs.py:734-737; counts allowed in ordering compares runs.py:1417-1419 | a walk from 0 sets cursors: runsc.py:821-847 | `for slot in 0 .. 026` / `for other in slot + 1 .. 027` frame.runs:66,70 | the slot passed to form 1 | No, same as 1 |

### Refused forms (verified by experiment)

| Exp | Shape | Result |
|---|---|---|
| A | `processor torpedoes_left(ship, flight)` reading `flight.torpedoes[ship]`; `run torpedoes_left(0, ship_flight)` | `frame.runs:35: unknown name ship_flight (a Record is read by its fields)`: runs.py:1391 |
| A2 | same Processor, `run torpedoes_left(0, 0)` | `frame.runs-prim:17: not a Record field: ('index', ('field', ('name', 'flight'), …` (runs.py:1366) |
| B | one `take_controls(turn)` with `rar(handoff.control_word, turn)`; `run take_controls(0)` / `(4)` | `network first_spaceship: run take_controls passes turn as a value (spaceship.runs:14); a value goes through a Record`: runs.py:1203. `runsc.build` re-runs `runs.check` (runsc.py:4524), so purity cannot be skipped there |
| C | `collision(slot, other, boom)` setting `objects.routine[slot] = boom`; `run collision(slot, other, explosion)` | `run collision passes boom as a value`: runs.py:1203. check_types would accept the enum member (runs.py:1847, 1874-1889); purity refuses it |
| E | `run spaceship(0)` inside `first_spaceship(slot)` (`spaceship` is bound) | `BindError: run spaceship passes only the slot the cursors point at`: runsc.py:1743 |
| F | B rewritten as a label: `take_controls(ship)` reads `control_bits.turn[ship]`, a new 2-slot table of constants {0, 4}; `run take_controls(0)` / `(1)` | **The evaluator accepts it** (pure: `ship` only indexes). runsc folds the table per copy, and the back end then fails: `Error: shift count 0 out of range` (tools/pdp1cc/select.py:213). The form works. This instance fails only because the first ship's copy becomes `rar(x, 0)` |
| G | `place_torpedo(new)` indexing `objects.*[new]` with no `reads: launch`; `run place_torpedo(launch.slot)` | **The evaluator accepts it.** runsc fails: `after_outline: no cursor for objects.x on the slot launch.slot holds: no routine indexes it by launch.slot` (runsc.py:2336). `derive_cursors` scans Processor bodies *before* argument substitution (runsc.py:852-859), so a Record-held slot must appear literally in some body |

One more fact from the code. At run time the evaluator's `Machine` would carry a Record as a value: `eval` of a Record name returns `("record", n)` (runs.py:844-846), and `field` of that value reads it (runs.py:853-857). Only the static checks (runs.py:1391, 1366) and `bind`/`place` for writes (runs.py:822-829) stop a Record-valued parameter. So binding a Record to a parameter takes an evaluator change, which is out of scope for #45.

## Form by form

### 1. Slot parameter (`run p(slot)`)

- **Parse and bind.** `run name(args)` takes any expressions (runs.py:421-433). `Machine.run` binds them to the callee's parameter names as locals (runs.py:687). Arity is checked at runs.py:1494-1499.
- **What a parameter may do.** `label_only` (runs.py:1228-1256) accepts a parameter only inside an index (`tree[2]` of an `index`, :1242), as a `for` bound (:1247-1248), or passed on to a callee that uses it the same way (:1243-1246). It reads the body only, not `requires:`. `requires: slot < 2` (spaceship.runs:12) passes because runs.py:1417-1419 lets an ordering compare take a parameter on its left.
- **Compiler, unbound routines.** These are inlined at each run with parameters replaced by arguments (`substitute`, runsc.py:130-140; call at 1763). Each copy gets its own words (`own_copy`, runsc.py:1789-1815).
- **Compiler, bound routines** (named in `pdp1/*.toml`: `spaceship`, `inertia_x`, `explosion`, …). The run must pass exactly the caller's own same-named parameters: `args != [("name", p) for p in params] or not set(params) <= set(r.params)` → BindError (runsc.py:1740-1743). The slot travels in the cursors, not as a value.
- **Binds:** a slot of a collection the body names. **Cannot bind:** a Record, a field, or a value.

### 2. Constant argument (`run show_magnitude(0)`)

- Same evaluator path as form 1. A literal slot past the collection is refused statically (runs.py:1378-1380).
- **Compiler.** The literal is substituted in. A collection field with all-numeric initial values that nothing writes is a *table of constants* (runs.py:1550-1580). Each mention at a literal slot becomes the number itself (runsc.py:143-163; "as each expansion of a macro holds its arguments"). `magnitudes.first/past/intensity[m]` fold this way into the four `dislis` expansions. A non-literal index into such a table is a BindError (runsc.py:159).
- **Binds:** a fixed slot, and through a constant table any per-site constant, as long as the parameter only indexes. That is the pure way to write B. Experiment F shows the evaluator takes it.
- **Bound routines** take no constant (experiment E). `calc(027)` works only because `calc` is a `match` whose arms pass the scrutinee's slot (runsc.py:1823, 1834-1836).

### 3. Slot held in a Record (`launch.slot`)

- The evaluator indexes with any number expression (runs.py:826-828).
- The compiler derives a cursor for each table field a bound routine's own Processors index by a held field (runsc.py:852-864). The cursors must be homed in one unit (runsc.py:860-864).
- A Network can pass such a field as a slot argument (evaluator OK, experiment G). The compiler finds cursors only from literal `field[holder]` text in bodies, so moving the holder into an argument fails unless some body still indexes by it.

### 4. Handoff and call Records

- Plain Records (`game record handoff`, spacewar.runs:403-430; `multiply_call`, `integer_divide_call`, …, spacewar.runs:277-330), read and written through declared contracts (runs.py:1035-1044, 1700-1718).
- **How the Network binds.** Order alone decides which value a shared body sees. The body reads a handoff field, and the Network runs an adapter before it that loads the field from the Record of its choice:
  - `warp_from_x(slot)` loads `handoff.coordinate` from `objects.x[slot]`, and `warp_from_y` loads it from `handoff.position`. Both feed one `torpedo_space_warpage`, which reads `handoff.coordinate` and writes `handoff.acceleration` (objects.runs-prim:76-83, tunables.runs-prim:26-28, objects.runs:37-42).
  - `inertia_x(slot)` takes its force from `handoff.acceleration`, which is set by `coast` in the explosion, by `torpedo_space_warpage` in the torpedo, and by `push_x` in the spaceship (arithmetic.runs-prim:347-359).
  - `integer_divide` is called twice, loaded by `aim_pull_x` and `aim_pull_y` (spaceship.runs:49-52, spaceship.runs-prim:99-113).
  - Minskytron's `pick_shift` runs six times through `shift_pick` (programs/minskytron).
- **Compiler.** For a bound JDA/JSP routine, the call Record's fields *are* the PDP-1 arguments: the `set`s of the callee's parameter fields just before the call become AC, IO, the entry word, or by-name words (runsc.py:1923-1954, `Bound.params` 431-454). A missing set is a BindError (runsc.py:1952). The shared body compiles once.
- **Binds:** values, never Records. The adapter still names the caller's Record and field.
- **Stateless?** The shared body names only its call Record, which is its interface and belongs to no caller. It does not name zero Records.

### 5. `match` dispatch

The Network picks *which routine* by an enum field (runs.py:755-761; all arms, one enum: 1502-1508). The compiler requires each arm to run the routine the member is spelled as, passing the scrutinee's slot (runsc.py:1817-1837). It chooses a Processor, not its Records.

### 6. Sub-Network contracts

`reads:`/`writes:` on a Network are checked against what its Processors touch (runs.py:1303-1348). They state which Records cross the boundary. They do not rename, alias, or substitute. No codegen in runsc.py reads a Network's `reads`/`writes` (the only `.writes` uses, runsc.py:3187 and 4330, read *Processors'* `writes`). A contract makes a bundle's boundary visible. It does not bind.

### 7. `for` loop variables

A Network `for` supplies the slot that form 1 passes (runs.py:734-737). The compiler turns a `for` from 0 into a cursor walk, and an inner `for … in slot + 1 ..` into the "other" walk (runsc.py:821-847).

## Can two call sites with different Records share one Processor body?

**No.** No form the evaluator and compiler accept today does this. The evidence:

- A parameter carries only a slot (runs.py:1228-1256, 1201-1205). A Record name is not an expression (runs.py:1391). A field place must name a Record literally (runs.py:1362-1366).
- Field names are strings in the tree, not `("name", …)` nodes, so even the compiler's `substitute` (runsc.py:130-140) could not swap them.
- The text already shows the cost:
  - `inertia_x` and `inertia_y` are the same body over `dx/x` and `dy/y` (arithmetic.runs-prim:347-359).
  - `take_first_controls` and `take_second_controls` differ by one shift.
  - `warp_from_x` and `warp_from_y`, `push_x` and `push_y`, `aim_pull_x` and `aim_pull_y` each differ only in the source.
  - Minskytron's `keep_ya … keep_xc` are six copies.

**Nearest forms:**

1. **Handoff/call Record (form 4).** One body over its own interface Record, with a per-site adapter that names the site's Record. This is the only form where one body serves different Records today. It compiles to one subroutine when the body is bound.
2. **Slot of a shared collection (forms 1-2).** When the varying Records can be slots of one collection, one body serves them all, and the Network passes which slot. Per-site constants go through a table of constants indexed by a constant label (experiment F: the evaluator accepts it, and that particular instance trips the back end on `rar(x, 0)`). Folding `x`/`y`-style field pairs into a slot axis would change the Records' shape and the declarations that lay them out (`pdp1/*.toml` names fields such as `objects.x`). That shape has not been tried.

## Reproduce

```
cp -r runs <scratch>/X    # edit as in the table above
RUNS_SOURCE=<scratch>/X uv run -q python tools/runsc.py | tail -2
```
