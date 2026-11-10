# Rule: a staged value held as the code of its use

Written 2026-11-09, before any compiler code for it. It states one compiler rule in machine-neutral terms, with no name from Spacewar or the Minskytron, then the PDP-1 back end's form of it and the programs that use it. It replaces the rule of `generated-code.md`, which the census refuted: no program outside Spacewar's lineage builds code from a command list, but at least four choose an instruction from data at one stage and run it at a later one.

## The rule

A value written at an earlier stage and read at a later one may be held as the compiled code of its use.

- **Stages.** The Network gives them. A Processor writes the value, and a different Processor, which the Network fires after it, reads it. The reading statement is the value's **use**. The writer usually fires rarely (at a start, a new game) and the reader often (every pass), but only the order matters.
- **The code of the use.** The words the compiler produces for the use, by its ordinary rules, with the value fixed. The value is then not stored as a number: its word or words are that code, and the use runs them where it stands instead of computing with a number.
- **The binding chooses the storage, never the code.** For each field, the binding says whether it is held as plain data or as code, and where its words lie. The text is the same either way, and so is every firing of the evaluator. The words come from the text and the compiler's rules.

A store of the value at the earlier stage is a store of its code. A copy of the value from one field to another is a copy of the words, so both fields must have the same use. A value fixed in the text (an initial value, a number set) is code the compiler builds. A value computed at run time fills the part of the code it decides (a hole) at the store.

## One rule, two sizes

The size of the code is the size of the use. One code path compiles both.

**One instruction.** The use is one operation whose operand is the value, such as a shift by a count. The value is held as that one instruction, and the use executes it (an execute instruction naming the word, or the word itself standing where the use runs). Programs: the Minskytron (`sh0`-`sh5`, picked from `gst` at start, run by `xct` every pass); Spacewar's explosion (`mi1`, an `scl` built from a random number, run in place); the music player, Expensive Typewriter and the Desk Calculator store instructions chosen at start into fixed sites (census, `generated-code.md`).

**A run of instructions.** The value is a member of a collection that a walker reads in order, taking one arm of a dispatch for each member. The use is that dispatch, so the code of a member is its arm, and stepping to the next member is falling into the next member's code. The collection is held as its members' arms laid end to end, and the walk is a jump to where it starts. A field read in an arm as the place the walk goes on from (`set at = L.f[at]; continue`) is held as the jump there: a one-instruction use inside the run. Program: Spacewar's outline (`oc` writes the arms at each new game; each frame `sp5` jumps into them).

The run form has one program, Spacewar's lineage, as the census found. It is the same rule as the one-instruction form, applied to a use that is a dispatch instead of one operation; it adds no rule of its own beyond what laying a run at a run-time address needs (below).

## What the compiler does

1. **Find the use.** The one statement of the reading Processor that reads the field. For a collection's field of an enum, the use is the dispatch on it. `runsc` refuses a held field that is read by the Processor that writes it, read in more than one use, or copied to a field with another use.
2. **Compile the use as a template.** `runsc` compiles the use with its statement compiler, as it compiles every Processor, and emits it as a C function of the dialect marked `TEMPLATE`: one per member for a dispatch, one per field for an operation, with the value as a parameter where it varies. `pdp1cc` compiles the template with its ordinary instruction selector and register tracking. It lays none of its words out in the image: they are the constants the stores below use.
3. **Store the code.** At each store of the value, `runsc` emits the dialect's store of the template: `CODE(t, v)` is the one word of template `t` with its value `v` (a constant word when `v` is a number of the text, built at run time otherwise), and `LAY_OUT(p, t, ...)` stores each word of template `t` through cursor `p` and steps it (`*p++ = w`). `pdp1cc` expands both into ordinary statements and lowers them by its ordinary rules: a word of a template is a literal constant (`lac (w`), so the generator's stores are the original's `lac (w / dac i p / idx p`.
4. **Run it.** One word laid out as a data word is executed by name (`xct w`); one with no data word is the instruction at its use. A run is entered by a jump to where its first member lies (the binding's existing `carry`).

**Holes.** A word of a template whose field the value decides at run time is a hole, filled at the store. A count from a mask (`popcount(w & m)`) fills a shift's count field by `ior`. A held jump in an arm (`back`) is the word of the field held there, copied in. A jump within one arm to another word of the same arm is relative to where the arm lies: the store builds it from the cursor (`add (k / dap w`), in a word the compiler lays out with the routine's data. Any code laid down at a run-time address needs its own jumps placed this way; it is part of the run form, not a separate rule.

**The unset word.** A held field with no value yet, on the tape, holds its code with no value: the halt for a count (`hlt`, as `sh0, xx` and `mi1, hlt`), and a jump to itself for a place (`jmp .`, as every jump the PDP-1 patches before it runs).

### Why a C template, and not another design

- **A second selector in `runsc`** (the rejected `tools/staged.py`) translated the walker's statements into instruction words by matching their shape. It duplicated `pdp1cc`'s selection for one routine, so an arm `pdp1cc` would compile differently, or a statement it handles that the matcher does not, fails silently or not at all. A C template has one selector: the arm compiles to exactly what the same statements compile to anywhere else.
- **Hand-kept machine text in the binding** (the rejected binding substitution) puts instruction words in `pdp1/`, which holds layout, never logic.
- **Lay the walker out as a routine and copy its words at run time.** The image does not hold the arms as code anywhere; it holds their words only as literal constants, which the stores read. A copy loop would add words the original lacks.
- **The template in C** keeps the division of labor the build already has: `runsc` decides what each RUNS statement means for the PDP-1 (registers, flags, pool words, the display's pulse), and `pdp1cc` decides the words. The stores are dialect statements, so every peephole `pdp1cc` already has applies to them unchanged (`idx` leaves the cursor in AC, so `dap` and `add (k` after a store need no load).

## Supporting idioms

Each is a general rule of the back end, not part of the held-code rule. The held code's stores need them to reach the original's words; each also fits a second program.

**Shared endings (cross-jumping).** Where several paths join and each ends with the same words, one copy of those words is kept, on the path that falls into the join, and each other path jumps to the first word they share. The shared words may begin mid-statement: paths that load different values and store them the same way share the store. It is a `pdp1cc` pass over a routine's words after selection, so it applies to any code, held or not.

- Spacewar `oc`: the arms for codes 2 to 5 end `lac (y / jmp oce`, sharing the step's last store, the swap, the `ioh` and the point with code 1's arm; code 6's two arms end `lac (w / jmp ocd`, sharing the last store.
- DDT (`ddt.mac`): `pls`, `min` and `isc` end `lac X / jmp ssn`, sharing `ssn, dip sgn` and what follows with the path that loads `lac cun` and falls into it.
- The music player (`pdp1m16.mac`): `lac tem / jmp cp3` shares `cp3, dac tpg` with the default path `cp2, law 252`.

**A store routine that lays IO through the cursor.** A JSP routine that stores IO through the generator's cursor and steps it, once or several times. The generator calls it where the words to store are IO's word, repeated as many times as the routine stores it. The binding chooses the routine and the Processor after which IO is loaded with the word, the way `args_done` chooses where a routine steps past its inline words; the word itself comes from the templates.

- Spacewar `ocs`: `dio i oc / idx oc` twice, called for the swap (`rcl 9s`, `rcl 9s`) of each step; IO is loaded once a code, after the code is taken (`lio (rcl 9s`).
- The music player (`pdp1m16.mac`): `put` ("jsp put to put IO in compiled area"): `dio i cb / idx cb`, called after each pitch or time is built in IO.

**The text's shape: decode once, walk often.** The music player is also the precedent for the text the run form compiles from: it decodes a score into a "compiled area" of data (`cb`, `put`) and the player walks it later. That is the same pure shape as a decoder writing a collection of members and a walker reading them; the player holds the area as data, Spacewar holds it as code. The binding is the only difference.

## What the binding says

- Which fields are held as code. Nothing else about the code.
- Where their words lie, in the vocabulary it already has: a data word (`fields`, `slots`), no word of its own (the instruction at its use), or a collection's words from an address the layout fixes, with the number of words reserved (`[addresses]`).
- For a run: the store routine and its IO load point, if the generator uses one; which words of the walk live in IO (`[[code]] io`), and whether points wait for the display's pulse (`pulse`).

It names no instruction, no word count of a template, and no expression.

## What it assumes, each a test against an occurrence

1. **One use.** Each held field is read in one statement of one Processor (and copies with the same use).
2. **Two stages.** The writer and the reader are different Processors, the writer fired first.
3. **Code the selector can produce alone.** The use compiles to words that run with nothing but the registers and fixed words: a run's arms enter and leave with the same register assignment, and a run is entered by a jump and left by a jump to one fixed place or by falling into the next member.
4. **A finite value set or a hole.** An enum member (one template each), a number of the text (a constant word), or a value that fills one field of one word.

An occurrence that needs any other difference shows the rule is too narrow.
