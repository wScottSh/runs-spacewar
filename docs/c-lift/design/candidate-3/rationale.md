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

Phase F steps 1-4 (synthesis.md) are implemented for the sqt subset. This section records where the code differs from this design and why.

**Front end.** pycparserext 2026.1 (`GnuCParser`, over pycparser 3.11, pinned in `uv.lock`) keeps `__attribute__((pdp1_*))` in every position the dialect uses: before a function, on a parameter, before a declarator, and after one (`word *mdx POOL`). The `_Pragma` fallback is not needed. `front.py` runs `gcc -E -D__PDP1CC__ -include pdp1.h` and keeps line markers, so errors name the C line.

**Header.** `pdp1.h` lives in `tools/pdp1cc/include/` and has two readers. pdp1cc sees typedefs and attribute spellings. g++ (`-std=c++14 -include pdp1.h`) sees candidate 1's `word` class, the executable reference. The plain-C mode and `normalize.py` are gone. A plain C compile is an `#error`. Comparisons abort unless the right side is 0, so a C comparison the skip group cannot make fails in the reference build too.

**Rule ids.** The registry is `tools/pdp1cc/rules.py`. Changes from the tables above:
- `EX-STORE-ZERO` (`dzm`) and `EX-LOAD-IO` (`lio`) are separate ids, so coverage shows each.
- `JDA-ENTRY`, `JDA-PROLOGUE`, `LAY-EXIT`, `RET` and `CONTINUE` name the words the Calls and Control tables describe in prose.
- The skip word carries `IF-SINGLE` or `IF-MULTI`, with the condition in the trace note. The skip table is not a rule id. The `cmpall` corpus program runs all twelve AC skip forms in SIMH.
- `x > 0` emits `sma+sza-skip i`, not `spq`. `spq` and `szm` are defined by the Spacewar source, not by macro1, and a standalone corpus program has neither. G3 also forbids Spacewar symbols in the compiler.

**TRACK.** Lowering is a pure function of (statement, AC/IO state). A `for (;;)` body is lowered again until the state at its head is a fixpoint. A read of an AC local whose value is no longer in AC is a compile error that asks for a static.

**Labels.** Generated labels use a per-region prefix from `lift.toml` (`zs` for sqt), not a region letter. Two labels that land on one word are merged.

**Splice build.** The interface check reads the source text. A label defined inside the region and named outside it must still be defined by the compiled text. It does not use the oracle xref. On a mismatch, `build` reports whether the `variables` base moved, then the first differing address with the expected word, the actual word and the rule id. There is no per-region cache.

**Gates.**
- G1 runs as `tools/check-*-reference.py`, one per lifted routine group. Each compares the native build of the lifted C with SIMH running the routine in the oracle `.rim`, in one SIMH session. sqt covers 0..0177777.
- G2 (`pdp1cc gate`) compares the AC result and every placed word after every call.
- G3 is `tools/check-g3.py`.
- G4 is structural: `Word.rule` is required and checked against the registry.
- G5, G6, G7 and the row checker are not built.

**Not implemented yet.** POOL, HOMED, JSP, XCT, INLINE parameters, while/do/switch, `sas`/`sad`, and the hints.

### M1 math (sin/cos, imp/mpy, idv/dvd)

Regions 190-254, 257-301 and 346-396 compile from `lift/sincos.c`, `lift/multiply.c` and `lift/divide.c`. The `mult` macro definition (195-198) is inside the sin/cos region. Its only users were the six calls in sin, which are now C calls. `tools/check-{multiply,divide,sincos}-reference.py` compare each routine with the oracle in SIMH.

New rules, each used by at least two corpus programs (`clamp`, `longdiv`, `polyeval`, `scaledmul`):
- `GOTO`. C labels and `goto`. A label can sit on any statement, including the body of an `if` (`if (a < 0) reduce: a += TWO_PI;`). TRACK takes the meet over every jump into a label and lowers the function again until the label states are a fixpoint.
- `JDA-CALL`, `JDA-BYNAME-ARG`, `BYNAME-READ`, `RET-INDIRECT`, `ARGS`. These cover calls and BYNAME parameters. The first read of a BYNAME parameter is the cell R (`R, xct`), and later reads are `xct R`. Returns are `jmp i R`. `inline.py` places `idx R` before the first top-level statement where three things hold. All by-name reads come before it. No jump crosses it. AC is dead there.
- `TAIL-CALL`, `LAY-FALLTHROUGH`, `LAY-ADOPT`. A JDA function whose returns all tail-call one BLOCK patches that block's exit. Its jump is elided when the block comes next in the layout. A BLOCK can take a `register` parameter and BYNAME parameters. Its callers pass their own, unchanged.
- `EX-STEP` (`mus`, `dis`), `EX-MOVE`, `EX-CONST-IO` (`cli`), `EX-STORE-IO` (`dio`), `LOOP-UNROLL`, `ST-ENTRY-CELL`, `SKIP-RETURN`.
- `EX-ROT` now also covers `ral`/`rar` on AC, `ril`/`rir` on IO, and `rcr`/`scl`/`scr` on the pair.
- `via`. Some rules shape a word but emit no word of their own: `LOOP-UNROLL`, `LAY-FALLTHROUGH`, `LAY-ADOPT` and `ST-ENTRY-CELL`. `Word.via` records them, and rule coverage counts them.

Deviations from the design, and why:
- **AC/IO moves are `rcr 9s` twice, not `rcl 9s` twice.** `register word m = h;` (AC to IO) and reading a register local into AC both lower to `EX-MOVE`. A half turn of the 36-bit pair is the same exchange in either direction. All three M1 moves use `rcr`. The design's default was the `swap` macro (`rcl`), which no M1 site uses. Pure moves written with `swap` (for example `lat` / `swap` at source line 838) will need a counted hint. A swap where both halves are live is written `rcl(h, l, 18)` and needs no hint.
- **mpy no longer reads an uninitialized register.** Candidate 3 wrote `rcr(h, m, 18)` with `m` uninitialized. The lift writes `register word m = h;`. After the move, TRACK records that AC holds nothing, so any later read of `h` is a compile error. The unrolled loop is `i < 021`, which C reads as 17.
- **`skip_return()` is new.** dvd and idv return to call+3, or to call+2 when the quotient overflows (|high dividend| >= |divisor|). `skip_return()` is `idx R`. In the reference build it counts how far past its inline words the call returns. Callers (`jda idv / lac \t1 / opr` in M6) have no C form yet. That is an open question for M6.
- **A JDA `register` parameter is IO at entry.** dvd takes its low dividend this way. idv's `scr 9s; scr 8s` shifts the caller's IO sign into the low dividend's last bit, so `integer_divide` also takes `register word lo`. In 200,000 native samples, flipping that bit changed no result. The C keeps the parameter because the machine reads IO.
- **ENTRY_CELL may give one cell several names.** In sin/cos, cos's entry word is `x_squared` and later `result`. In divide, idv's entry word is `quotient`, which holds |divisor| on the overflow path. Assigning between two names of one cell emits nothing. That generalizes "assigning a param to its own ENTRY_CELL alias".
- **Symbols.** `SYM("x")` pins a symbol. A file-scope name of up to 6 characters is its own symbol, and a longer one gets a generated symbol (region prefix and counter). C labels always get generated symbols.
- **ARGS placement uses statement boundaries, not word-level dominators.** It runs on the IR, not on words. It covers mpy, imp and dvd, and corpus `longdiv` places the skip early. `ARGS_DONE()` is still unimplemented because nothing needs it.
- **SIMH runs without the multiply/divide option** (`set cpu nomdv`). SIMH enables the option by default, which turns `mus` and `dis` into full multiply and divide. Spacewar 3.1 assumes a machine without it.
- **Harness.** A corpus entry or reference check can take AC, IO and one by-name word. Each call compares AC, IO (for `dword` results) and the return point. The oracle helper lives in `tools/oracle_check.py`, outside the compiler tree that G3 lints.
- **Lifted coverage.** `pdp1cc build` reports how many words of the final image come from compiled C, out of all words placed. The constants pool counts as unlifted because the unlifted `constants` directive places it.

## Open questions and risks

- Runtime-generated code: is "`insn` values + `jump(sp5)` + exported label `sq6`, with `pdp1_exec` as a header-only specification" an acceptable genuine C form to the operator, or does the specification count as an interpreter? This is the weakest idiom.
- `mex` builds `scl n` at run time (`ior (scl`) and executes it in place at `mi1`. That needs a "slot" (a writable one-word XCT routine) beyond the examples. Is `SLOT dword mi1(dword)` acceptable?
- Uninitialized `register` reads (mpy's `rcr(h, m, 18)` with garbage IO) are indeterminate in ISO C. The reference build maps IO to a global so it is defined there. Is that acceptable?
- `ENTRY_CELL` aliasing (sin/cos scratch, oc's pointer) is only correct while the owner's parameter is dead. Should the compiler prove that, or is a documented contract enough?
- pycparserext must parse GNU attributes on parameters and labels before declarations. A front-end spike should confirm this before anything else.
- `dislis` x4 (static inline + `int` params, per-instance homed cells, `jmp flo+R+1`) is untested against these rules.

## Next implementation step

Build `skips.py`, `select.py`, and `emit.py` for the sqt subset, then make `pdp1cc lower examples/sqt.c` output assemble to the oracle hash through `splice.py`, with the G2 corpus started in the same change.
