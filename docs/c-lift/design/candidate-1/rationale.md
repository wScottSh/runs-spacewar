# Candidate 1: register-explicit C with homed pointers, link-aware ABIs, and JIT-style codegen

## Problem

Spacewar 3.1 has to become human-readable C that a general compiler (swc) turns back into the byte-identical `.rim`. Three things make the shape non-obvious.

1. **No free choices.** Every word is fixed, so every choice a compiler would normally make has to be fixed too: AC or IO, `law` or literal, which instruction hosts a pointer, where a return jump sits.
2. **Order leaks into addresses.** The literal pool and the `\` variables are ordered by first appearance in the emitted text. Pass 1 reserves one pool slot per literal *occurrence*, duplicates included, so the variables block address depends on the total count (`tools/macro1.c` `literal()`, `lookup()`).
3. **Self-modifying code needs real C.** The operator rules out asm, interpreters, and memorized output: self-modifying code needs a genuine C form, and the compiler must be rule-based.

The constraint that shapes everything: when swc has a choice the C does not settle, it either follows a fixed rule or the C settles it explicitly. swc never guesses toward a known answer.

## Usage (caller's view)

```c
#include "spacewar.h"

#pragma pdp1 jda(sqt)                         /* entered by jda; n lives in the entry word */
word sqt(word n) { ... }

#pragma pdp1 jda(mpy, inline=b:exec)          /* b is the caller's next instruction */
dword mpy(word a, word b) { ...; consume(b); p.ac = mp2; return p; }

#pragma pdp1 xct(tvl)                         /* a one-instruction function, run in place */
word tvl(word v) { return v >> 4; }           /* 00007: sar 4s ; call site: xct tvl */
```

Call sites, from `examples/`:

```c
th = mpy(ral(x, 2), 0242763).ac;    /* ral 2s ; jda mpy ; lac (242763 ; dac sin */

mx1: mx2: mt1 = mag(*mx1 - *mx2);   /* mx1: lac . ; mx2: sub . ; spa ; cma ; dac \mt1 */

*oc_to++ = LAC(&sx1);               /* lac (lac \sx1 ; dac i oc ; idx oc   (runtime codegen) */
sp5: (*sp5)();                      /* sp5: jmp .    enter generated code; it returns to sq6 */
```

To build: `swc build` splices each region's C into the source, assembles it, and checks the sha256.

## Shape

**Data structures first.** sema decides one `Storage` per object (entry word, homed host, homed data word, inline, placed, Macro variable, overlay, AC, IO, AC:IO) and one `Abi` per function (jda with optional exec/data operand, jsp, jmp, xct). Lowering reads these and never infers them. Every IR `Word` carries the rule id that made it. The one mutable analysis is the AC/IO value cache (R2), which is per-block and intersected at joins.

**Load-bearing decision 1: registers are C locals, and the compiler checks them instead of allocating them.** `auto word` is AC, `register word` is IO, and `dword` is the AC:IO pair. There is no spilling. A right operand must be a memory operand, and swc refuses to invent temporaries. Register dataflow is visible in the C, so the output is deterministic, and the remaining freedom is closed by small rules: S1 constants, F1 skips, L1-L3 if layouts, and an R2 cache that drops redundant loads. That cache is what makes `dac sin; jda mpy` and the cos-into-sin entry past `lac sin` come out without special cases. Principle: per encode-lessons-in-structure, a choice the author made by hand in 1962 appears in the C (operand order, `swap` vs `swapr`), not in a compiler heuristic.

**Load-bearing decision 2: self-modification gets three C forms, and none of them is an interpreter.**

- **Homed pointers.** A pointer whose storage *is* an instruction's address field, chosen by labeling the statement with the pointer's name (H1-H4). The 14 main-loop cursors, `ocg`, `sr3`, and `sp5` are ordinary C pointers. `idx`, `dap`, `lac i`, and the `(lac mtb+30` bound all follow from one fact: the rvalue is the host word.
- **ABIs with first-class links.** jda entry words are parameters. The return slot is the last `return`. An exec inline operand is a by-name parameter read via `xct`. `consume(p)` (a no-op in C, like `va_end`) marks the `idx link`. Shared exits are tail calls (C4).
- **Runtime code generation is a JIT, written the way C JITs are.** It uses instruction encoders (`LAC(&sx1)`), a store cursor, and a code-pointer call whose ABI (`jmp`, `returns_to(sq6)`) is declared on the function type.

The tunable table's executed constants become one-instruction functions (`xct` ABI). The source's own comment, "may be replaced by jda or jsp", becomes a one-pragma change.

**Load-bearing decision 3: layout is source order, and placement belongs to macro1.** swc emits in C order, uses `.±n` for unnamed targets, and never computes an address, a pool order, or a variable order. Literal and variable ordering then follow from the C. The one global hazard, literal occurrence count moving `variables`, is the splice diff's first check.

**Interface depth.** The public surface is one header: four types, about 45 builtins and instruction encoders with C reference bodies, and 15 pragma forms. Behind it sit liveness, the value cache, skip polarity, slot placement, homing, pool behavior, and the splice gate. `pdp1.h` is also the semantic oracle. Under `g++` the same C runs natively with ones' complement `word` operators. Lifted `sqt` matched sqrt×512 exactly. Lifted `sin`/`cos` matched libm within 6.2e-5. Writing the reference run caught a real bug: Macro `repeat 21` is octal, so it means 17.

**What it deliberately does not do:** spill, reorder, pick instruction variants heuristically, or read the original source.

## Synthesis decision

*(Filled in by arena.)*

## Tradeoffs accepted

- We accept the C showing register placement (`register`, `dword`, `.io`) in exchange for deterministic output without a search. The C reads as low-level C, not as idiomatic application C.
- We accept explicit `consume(p)` in exchange for not inventing a scheduling rule. The three originals bump the link at three unrelated points (right after a call in imp, at a join in mpy, after an unrelated store in oc).
- We accept `place` and `homed_word` pragmas for data words embedded in code (sq1/sq2, ocm/ocn) in exchange for not reordering anything.
- We accept two spellings of the AC/IO exchange (`swap` = `rcl 9s`×2, `swapr` = `rcr 9s`×2). The program really uses both encodings.
- We accept that the C++ reference build forces locals to the top of the function and bans tentative definitions, in exchange for an executable meaning.
- Two placeholder conventions (`jmp .` for return slots and homed hosts, `xct 0` for exec links) are ABI constants, not oversights.

## Alternatives considered

- **Expression C plus a search-based selector.** Write natural C and let swc search for the instruction sequence matching... what? Without the oracle there is no target, and with it the compiler is overfit by definition. This hides the most from authors and loses honesty.
- **Explicit-accumulator C (`AC = AC + x;` everywhere).** This is assembly in C syntax. Codegen becomes a 1:1 transliteration, which the operator would read as memorized asm.
- **A self-modification runtime (an `insn` interpreter in the reference build, `xct(insn)` as a function).** This gives every form one uniform C meaning, but it puts an interpreter inside the program's semantics. It also turns homed pointers into opaque memory pokes, which hides the dataflow the reader most needs.
- **Attributes (`__attribute__((annotate))`) instead of pragmas.** gcc ignores unknown attributes with warnings and pycparser cannot parse them. No clang is installed. Pragmas survive cpp, pycparser parses them, and gcc ignores them.

## Implementation reconciliation

*(Empty until implementation.)*

## Open questions and risks

- Is `consume(p)` acceptable to the operator as "real C", given that its reference meaning is a no-op (like `va_end`)? Or must the bump point be derived?
- Do other regions reload a value AC already holds? If so they need `volatile` reads, and I found none in the examples I traced. Should swc warn when a `volatile` is only there to defeat R2?
- Unaddressed idioms that need a rule before their regions lift:
  - `bpt`'s computed jump into an unrolled `starp` block. Duff's device looks like the honest C form.
  - `mex`'s run-time-built `scl` (`ior (scl`, then `dac mi1`, then execute). A variable-mask shift builtin whose lowering patches and executes would cover it.
  - `msh, xct .` through a two-entry table of xct functions.
  - `dislis` uses `jmp flo+R+1` into another instance's data.
- S6 merges operate micro-ops only within one statement. A source site where two adjacent operate words were deliberately *not* merged inside one C expression would need splitting. None found yet.
- The SIMH side of the differential gate does not exist yet. Equivalence has only been checked natively.

## Next implementation step

Build `front.py`, `sema.py`, `lower.py`, `flow.py`, and `emit.py` for the subset `sqt.c` uses, plus `splice.py`, and get the hash to hold with region [309, 343] lifted.
