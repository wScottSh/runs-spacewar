# Candidate 3: storage-class C over symbolic Macro

## Problem

Spacewar 3.1 must be lifted to readable C that compiles back to the byte-identical `oracle.rim`. The operator rules out asm blocks, interpreters, and a compiler that replays memorized words. Three things make the shape non-obvious.

- Identical semantics often come with different encodings, and the binary records the authors' choice each time. Examples: `law 1 / add x` vs `lac x / add (1`, `sma` vs `spa i`, `rcl 9s` x2 vs `rcr 9s` x2, and where `idx R` skips the inline arguments. The C has to carry those choices without becoming assembly.
- Much of the state lives inside instructions: walking pointers in `lac .` address fields, return addresses in `xct` cells, jda arguments in entry words, and generated code in the object table.
- Two invisible orders in macro1 must come out right. The pass-1 literal count fixes the `variables` base. First-use order fixes every `\x` address and the literal pool order (`tools/macro1.c` `literal()`, `lookup()`).

## Usage (caller's view)

A lifter writes ordinary C against one header. The storage class says where each thing lives:

```c
extern word sq1, sq2;
JDA word sqt(word r) {              /* r is the entry word: input, then remainder */
    sq1 = -023; sq2 = 0;
    register word lo = r;           /* register = IO */
    r = 0;
    for (;;) {
        if (++sq1 >= 0) return sq2; /* isp / jmp / lac / exit */
        ...
        word a = r;                 /* automatic = AC */
        rcl(a, lo, 2);
        ...
    }
}
word sq1 = 0;                       /* initialized = placed right here */
```

The lifter places the self-modifying pointer's storage at the instruction marked `home`:

```c
HOMED word *ml1, *ml2;
word w = *home(ml1);                       /* ml1, lac .     */
ml2 = 1 + ml1;                             /* law 1; add ml1; dap ml2 */
} while (++ml1 != &mtb[NOB - 1]);          /* idx ml1; sas (lac mtb+30-1; jmp ml1 */
```

Runtime code generation is data writing plus a jump:

```c
*ocp++ = I_LAC(&sx1);                      /* lac (lac \sx1; dac i oc; idx oc */
ocn.addr = ocp + 4;                        /* add (4; dap ocn */
```

Then the build:

```
$ pdp1cc lower examples/sqt.c --trace     # Macro text, rule id per word
$ pdp1cc build lift.toml                  # splice every lifted region, macro1, sha256
  sqt       309-343    ok
  mainloop  843-941    ok
  oracle.rim 8744e9c9...bdf  MATCH
$ pdp1cc gate                             # honesty gate G1-G7 (compiler.md)
```

## Shape

**Data first.** The compiler has one output type, `Word(op, i, operand, labels, rule)`, and one placement type, `Storage`: AC, IO, Pool, Placed, Homed, Entry, or CompileTime. `dialect.py` decides storage from the declaration alone and never from use, so a reader can predict every load and store from the declarations. All operands stay symbolic, so macro1 still does all address arithmetic (per boundary-discipline: the assembler is the boundary).

Load-bearing decisions:

1. **The C storage class is register allocation.** Automatic is AC, `register` is IO, an uninitialized static is a `\x` pool variable, an initialized static is a word placed at its definition, `HOMED` is an instruction's address field, and a JDA parameter is the entry word. The compiler never invents a temporary or spills a value. If something needs a home, the error names the variable to introduce. That keeps the compiler's choices few enough to be rules, and it is what lets the hand traces match without memorization (per encode-lessons-in-structure: an illegal allocation fails to compile instead of being chosen silently).
2. **Self-modification is ordinary C over cells.** A homed pointer is a C pointer whose storage happens to be inside an instruction: `*home(p)` is the home, `*p` elsewhere is `i p`, `p = e` is `dap`, and `++p` is `idx`. Assignment to `insn.addr` is `dap`. An `insn` is a value with constant constructors. A one-word function is `XCT`. A shared exit is a BLOCK that callers adopt by tail-calling it. Each idiom keeps its C meaning: a pointer stays a pointer and a call stays a call. pdp1.h gives that meaning for a native reference build.
3. **Operand order and the skip table carry the authors' encoding choices.** `1 + p` emits `law 1; add p`. `p + 1` emits `lac p; add (1`. Conditions map through one exhaustive table, `skip_when`. The few choices that C semantics cannot express are hints with identity meaning: `SKIPNOT`, `ARGS_DONE`, `PLACE`, `RELOAD`. The gate deletes each hint and fails if the output does not change, so a hint is never decoration.

**Interface depth.** The surface is one header of about 30 names plus `pdp1cc build`. Behind it sit AC/IO value tracking, skip polarity, exit adoption, inline-argument skips, jump tables, unrolling, and both macro1 pool orders. The lifter never sees an address, a literal, or a label.

**Deliberately not done.**
- No optimizer beyond AC/IO value tracking and fallthrough elision.
- No CSE of literals: each occurrence counts toward the pass-1 total.
- No address computation.
- No interpreter in the output. `pdp1_exec` in the header is a reference specification for generated code only.

**Evidence.** The six example regions, 448 words, were lowered by hand with these rules. `examples/verify.sh` splices them into the source and gets the oracle hash, singly and all together. All six `.c` files pass `gcc -std=c11 -fsyntax-only -include pdp1.h` with zero diagnostics. Under `-Wall -Wextra` the one warning is the deliberately unused label `md1` in tunables.c.

## Synthesis decision

*(filled in by arena)*

## Tradeoffs accepted

- Some C reads as a transliteration where the arithmetic really is 36-bit register shuffling (mpy's `rcr(h, m, 18)` pairs). In exchange, no builtin has a fixed multi-word expansion, which would be memorized asm under another name.
- The lifter writes operand order to match the binary (`1 + ml1`, `HALF_PI + c`). In exchange there is a deterministic rule with no hint.
- `goto` and labels inside routines (sin's range reduction, oc's shared tails) stay where the original control flow is irreducible. In exchange, layout is simply source order.
- About one counted hint per routine with inline arguments (`ARGS_DONE` in oc), plus `PLACE` for static locals in mid-function. In exchange, the default rules stay simple.
- macro1 stays in the pipeline permanently. In exchange, pdp1cc never duplicates layout or pooling logic, and partial lifts splice for free.

## Alternatives considered

- **Compiler owns layout and emits absolute words.** This hides macro1, but the compiler would have to reimplement pass-1 literal counting, pool dedup, and variable allocation exactly, and partial lifts could no longer splice into source text. It hides less and duplicates the riskiest logic.
- **Implicit register allocation.** Locals are just C locals, and the compiler picks AC, IO, or memory with a cost model. The C would be cleaner, but every allocation choice the authors made would need a heuristic tuned to Spacewar. That is overfitting by another route, and it is hard to audit.
- **Machine-level intrinsics (`LAC(x); ADD(y);` as C calls).** Trivial to compile and byte-exact, but it is assembly in function-call syntax and fails the operator's constraint in spirit.
- **Runtime codegen as a C interpreter over an outline table.** Readable, but it changes the binary. oc must remain the code generator it is.

## Implementation reconciliation

*(empty until implementation)*

## Open questions and risks

- Runtime-generated code: is "`insn` values + `jump(sp5)` + exported label `sq6`, with `pdp1_exec` as a header-only specification" an acceptable genuine C form to the operator, or does the specification count as an interpreter? This is the weakest idiom.
- `mex` builds `scl n` at run time (`ior (scl`) and executes it in place at `mi1`. That needs a "slot" (a writable one-word XCT routine) beyond the examples. Is `SLOT dword mi1(dword)` acceptable?
- Uninitialized `register` reads (mpy's `rcr(h, m, 18)` with garbage IO) are indeterminate in ISO C. The reference build maps IO to a global so it is defined there. Is that acceptable?
- `ENTRY_CELL` aliasing (sin/cos scratch, oc's pointer) is only correct while the owner's parameter is dead. Should the compiler prove that, or is a documented contract enough?
- pycparserext must parse GNU attributes on parameters and labels before declarations. A front-end spike should confirm this before anything else.
- `dislis` x4 (static inline + `int` params, per-instance homed cells, `jmp flo+R+1`) is untested against these rules.

## Next implementation step

Build `skips.py`, `select.py`, and `emit.py` for the sqt subset, then make `pdp1cc lower examples/sqt.c` output assemble to the oracle hash through `splice.py`, with the G2 corpus started in the same change.
