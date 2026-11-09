# Candidate 2: cell-typed C, accumulator compiler, Macro text out

## Problem

Lift Spacewar 3.1 (PDP-1 Macro, 1962) to human-readable C that a real compiler
lowers back to the byte-identical `build/oracle.rim` (sha256 `8744e9c9...`).
Constraints from the operator: no asm, no inline assembly, no interpreter or
emulator, self-modifying code gets a genuine C form, and the compiler is a
general one (lowering rules over C constructs), not a lookup of memorized
assembly. The shape is non-obvious because the binary depends on things C
normally hides: where a routine's return address lives, which cell is both data
and instruction (`ml1, lac .`), the order in which literals and variables were
first mentioned (macro1 numbers them by first appearance, and reserves pool
space by literal *occurrences*, so even `law 1` versus `lac (1` moves the
`variables` address), and operand order the 1962 authors chose by hand.

## Usage (caller's view)

The consumer is the person lifting a region. They write dialect C against
`pdp1.h`, compile the region, splice it into the original, and read one
verdict.

```
$ pdp1cc lift/sqt.c -o out/sqt.mac        # Macro text, each line tagged  / @sqt.c:14 S6
$ lift build                              # splice every region in regions.toml, run macro1, sha256
sqt  ok   (prefix 3 of 3)  8744e9c9c854...     # illustrative output; no compiler exists yet
```

The C they write (full file: `examples/sqt.c`):

```c
PDP1_JDA word sqt(word x)             /* x IS the entry cell, as in the original */
{
    sq1 = -023;  sq2 = 0;  IO = x;  x = 0;
sq3:
    if (++sq1 >= 0) return sq2;
    sq2 = sal(sq2, 1);
    word r = rcl(x, 2);
    if (r == 0) goto sq3;
    ...
```

Self-modifying pointer code reads as pointers (`examples/mainloop.c`):

```c
w = HERE(ml1);                        /* the cell ml1 is here, and is the load */
...  ml2 = ml1 + 1;  ...              /* dap: patch the next cursor           */
if (++ml1 != (cptr)(mtb + NOB - 1)) goto ml1_top;
CALL_FN(*ml1);                        /* indirect call through the table      */
```

A tunable is a one-word operation or a data word (`examples/tunables.c`):
`PDP1_XCT word tvl(word a) { return sar(a, 4); }`, used as `tvl(sn)`.

On a mismatch the verdict names the first wrong address, the C line, and the
rule that produced it.

## Shape

**Data structures first.** Three typed notions carry the machine facts, so the
compiler does not rediscover them:

- `word`: an 18-bit ones' complement pattern. Operators on it mean the PDP-1
  operations; relational operators exist only against 0 (`spa`/`sma`/`sza` and
  their inversions), because a two-word comparison on this machine is a
  subtraction plus a sign test and the author must say which.
- `cptr`: a pointer whose home is an instruction cell. Written only by `p = q`
  (`dap`) and `p++` (`idx`), so its opcode bits are invariant; that makes the
  comparison `sas (lac mtb nob` (idiom 5) sound by type. `HERE(p)` puts the
  cell at this point in the code and executes it as the access; every other
  `*p` is indirect. The opcode is inferred from the surrounding expression.
- `inl_insn` / `inl_data` parameters: the caller's inline word after a `jda`.
  Reading one is `xct` of, or `lac i` through, the link cell, which is itself a
  cursor. Idiom 4 becomes a signature.

**Memory is the C file.** Layout is declaration order; initialized statics are
in the stream where defined; uninitialized globals are pool variables
(`\name`). No linker pass reorders anything. This gives idioms 2, 3 (entry
word as storage, `cos` into `sin`), 15 and 16 their C form with almost no
special cases: `ENTRY(f)` names the entry word, `PDP1_ORG` is `n/`, a return
cell is placed after the last `return`, and `cos` is `return sine(HALF_PI + x)`
lowered by link forwarding (C6).

**One register, no spill by default.** The compiler is an accumulator-machine
instruction selector. Function-scope locals live in AC while their live range
allows it (A1); IO is explicit (`IO = x`, combined shifts); a forced spill is a
compile error under `PDP1_NOSPILL`, which every lifted function uses. This is
what makes `x = a; a = mpy(a, x)` come out as `dac sin ; jda mpy ; lac sin`
with no reload.

**Compiler emits Macro text; macro1 assembles.** The literal pool and variable
numbering are macro1's job; the compiler's job is to never reorder, hoist, or
invent a literal or variable (L3). The incremental build splices compiled
regions into the original text and compares the hash at every prefix.

**Interface depth.** Public surface of the compiler: `compile(c) -> Macro text`
and `build(regions) -> Verdict`. Hidden: instruction selection, AC cache,
skip-microcode choice, jump-table lowering, call linkage, cell placement, and
pool/variable discipline. Public surface of the dialect: about 70 declarations in
`pdp1.h`, each with a C reference definition, plus 12 pragma markers. It is no smaller
because each name is a machine fact the original's behavior depends on
(per type-system-discipline: make illegal states unrepresentable).

**Proof status.** Six examples hand-traced; 467 rows machine-checked against
the oracle listing for text/word/address agreement (`examples/check_trace.py`).
Honest gap: the lowering is argued, not run, since there is no compiler yet.

## Synthesis decision

Filled in by arena.

## Tradeoffs accepted

- We accept `HERE(p)` as explicit syntax in exchange for placing a cell exactly
  where the original did. Inferring "first dereference" fails on `mb1`, which is
  dereferenced indirectly (line 892) 17 lines before its cell (line 909), and on
  `mom`, whose cell is in another routine.
- We accept authored-choice spellings in C (`IO = -04000; mtc = IO;` for the
  `load` macro, `rcr` versus `rcl` swaps, source-ordered operands) in exchange
  for a compiler with few heuristics. The cost is C that is a little less
  pretty than `mtc = -04000`.
- We accept that Macro text, not binary, is the compiler's output, in exchange
  for not reimplementing macro1's pool and variable rules. The identical-binary
  claim then rests on the oracle's own assembler.
- We accept function-pointer `CALL_FN(word)` and `PDP1_CONT` as the escape for
  indirect and cross-routine control, in exchange for not inventing label
  addresses in C.
- A tail-call rule (C6) that makes `cos` fall out is a policy ("always forward
  when legal"), which the hash can see. Kept because it is stated over C
  (`return g(e)` with a jda callee), not over `cos`.

## Alternatives considered

- **High-level C with inferred cursors and registers.** Smaller dialect, nicer
  C. Lost: placement of a cell is information the high-level C does not
  contain (`mb1`), and the inference would be a Spacewar-shaped heuristic. The
  chosen dialect has more surface but every name is a machine fact.
- **Per-opcode builtins (`LAC(x)`, `DAP(p)`).** Trivial compiler. This is
  assembly with a C accent and the operator rules it out; it also exposes
  every selection decision to the caller (maximum surface, zero hidden depth).
- **Core as a `word core[4096]` array with a flat C view of self-modifying
  code.** Genuine C, no new dialect. Lost: the C is then an interpreter-shaped
  port (an array standing in for memory), which the operator rules out, and the
  compiler would have nothing to select.
- **Emit the binary directly.** Removes the dependence on macro1. Lost: it
  duplicates the pool/variable/RIM-block rules macro1 already encodes, and a
  bug there is indistinguishable from a bug in the lifted C.

## Implementation reconciliation

None yet. Accepted deviations from this design go here with their acceptance
source, and the usage, signatures, and rule list above are updated in the same
change.

## Open questions and risks

- Is the dialect surface acceptable, given that each lifted function reads a
  little like "C that is aware it is the PDP-1"? Or should `rcr`/`rcl`/`IO`
  spellings be hidden behind inference at the cost of more heuristics?
- Should `mex`'s runtime-built, then executed, instruction word get an
  `EXEC_HERE` cell with a reference meaning limited to the shift group, or is a
  reference-less builtin unacceptable under the "C has meaning independent of
  our compiler" requirement?
- How far may `PDP1_CONT` go before it is a goto-across-functions in disguise?
  The `sq6` resume point forces a split of `ss1`; is that split readable?
- Do the `ONE-OFF` rules (S9, C6, C7) earn corpus witnesses, or are some of
  them overfit and better replaced by two spellings in C?
- Is the lockstep reference gate (section 6.8) worth a host model of `ENTRY`
  and `CALL_FN`, or is the corpus plus the hash enough?

## Next implementation step

Write `front.py` and the S1-S6/C1/C3/L1/L2 subset of `lower.py` and `layout.py`,
and make `examples/sqt.c` splice to the oracle hash.
