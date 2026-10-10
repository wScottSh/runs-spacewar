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

Phase F is complete: `pdp1cc build` compiles every word of the image from `lift/` (M8 section). This section records where the code differs from this design and why, milestone by milestone. A later section can supersede an earlier one; the M8 section says which parts of the splice-era contract are gone.

**Front end.** pycparserext 2026.1 (`GnuCParser`, over pycparser 3.11, pinned in `uv.lock`) keeps `__attribute__((pdp1_*))` in every position the dialect uses: before a function, on a parameter, before a declarator, and after one (`word *mdx POOL`). The `_Pragma` fallback is not needed. `front.py` runs `gcc -E -D__PDP1CC__ -include pdp1.h` and keeps line markers, so errors name the C line.

**Header.** `pdp1.h` lives in `tools/pdp1cc/include/` and has two readers. pdp1cc sees typedefs and attribute spellings. g++ (`-std=c++14 -include pdp1.h`) sees candidate 1's `word` class, the executable reference. The plain-C mode and `normalize.py` are gone. A plain C compile is an `#error`. Comparisons abort unless the right side is 0, so a C comparison the skip group cannot make fails in the reference build too.

**Rule ids.** The registry is `tools/pdp1cc/rules.py`. Changes from the tables above:
- `EX-STORE-ZERO` (`dzm`) and `EX-LOAD-IO` (`lio`) are separate ids, so coverage shows each.
- `JDA-ENTRY`, `JDA-PROLOGUE`, `LAY-EXIT`, `RET` and `CONTINUE` name the words the Calls and Control tables describe in prose.
- The skip word carries `IF-SINGLE` or `IF-MULTI`, with the condition in the trace note. The skip table is not a rule id. The `cmpall` corpus program runs all twelve AC skip forms in SIMH.
- `x > 0` emits `sma+sza-skip i`, not `spq`. `spq` and `szm` are defined by the Spacewar source, not by macro1, and a standalone corpus program has neither. G3 also forbids Spacewar symbols in the compiler.

**TRACK.** Lowering is a pure function of (statement, AC/IO state). A `for (;;)` body is lowered again until the state at its head is a fixpoint. A read of an AC local whose value is no longer in AC is a compile error that asks for a static.

**Labels.** Generated labels use a per-file prefix from `lift.toml` (`zs` for sqt), not a region letter. Several labels may name one word, and each stays a name of it (`zh73, zh17, jmp .`); M3 merged them into one (M4 section).

**Build.** Until M7 the build spliced compiled regions into the source text, with an interface check that a symbol unlifted text named was still defined. Since M8 it compiles `lift/` into one program (M8 section). On a mismatch, `build` reports whether the `variables` base moved, then the first differing address with the expected word, the actual word and the rule id. There is no per-region cache.

**Gates.**
- G1 runs as `tools/check-*-reference.py`, one per lifted routine group. Each compares the native build of the lifted C with SIMH running the routine in the oracle `.rim`, in one SIMH session, and compares every JDA entry word after every call. sqt covers 0..0177777.
- G2 (`pdp1cc gate`) compares the AC result, every placed and reserved word, and every JDA entry word after every call. Each rule needs two corpus programs that do not mirror a lifted routine (M2 section).
- G3 is `tools/check-g3.py`.
- G4 is structural: `Word.rule` is required and checked against the registry.
- G5 and G6 run in `pdp1cc gate` (M2 section). `tests/reject/` holds programs the dialect must refuse, each with the error it expects.
- G7 is a review rule: a new rule lands with its corpus programs. The row checker is not built.

**Not implemented yet.** while/do, indirect calls that return other than through a pointer word to a JSP function (M6) or a computed call `((f *)e)()` (M7), a homed pointer read as a value anywhere but in the value a `dap` stores or its home word, `int` parameters of static inline functions, and the hint `RELOAD`. POOL, HOMED, INLINE parameters, the jump-table switch, `PLACE` and `ARGS_DONE` landed in M3; `sas`/`sad`, static inline functions and Duff's device in M4; `SKIPNOT` and the computed call in M7.

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

### M2 tunables (start vectors, constants table, cwr slot, sbf)

Source lines 67-116 compile from `lift/tunables.c`. The words the game executes with `xct` are XCT functions, and the words it reads are placed words. `tools/check-tunables-reference.py` compares each XCT function with the oracle executed by `xct` in SIMH.

Review follow-ups from M1, landed first:
- **Shared storage in the reference build.** `pdp1.h` cannot spell two storage facts, so `gate/reference.py` binds them in a copy of each C file before g++ sees it. A JDA function's first parameter and every `ENTRY_CELL` name of it are references to one cell, `pdp1_cell_<f>`, which the call fills. A `BYNAME` parameter is a `const word &`, read again at every use, as `xct` reads it. A definition the binder cannot find is an error. Corpus `cellshare` differs from SIMH on 637 of 640 calls without the binding. The rewrites are textual and bind only `BYNAME word p` and `ENTRY_CELL(f) word x;`, so they fail closed. Outside comments, the count of each rewrite must equal the count of its attribute in the preprocessed source, or the build stops. A `/* reject-reference: */` program in `tests/reject/` is one the dialect accepts and the binder must refuse (`ENTRY_CELL(g) SYM("sen") word seen;`, `BYNAME const word b`).
- **Tail calls.** A function and the BLOCK whose exit it adopts must skip the same number of inline words. Only a function's final statement may fall into the next BLOCK; corpus `nibble` found that M1 dropped a jump that was followed by other code.
- **Symbols and attributes.** `SYM` text must be a Macro symbol that macro1 does not predefine (`macro.py` copies macro1's tables). A short C name that is not one gets a generated symbol. Unknown `pdp1_*` attributes are errors. All declarations of a function or object carry the same attributes, except `AT`, which belongs to the definition.
- **SKIP-IO.** The IO skip table has a rule id (corpus `iosign`, `revbit`).
- **Coverage.** A corpus header may say `mirrors=<routine>`. Mirrors (`longdiv`, `polyeval`, `clamp`, `scaledmul`) are listed and not counted. Interpretation of "credit a rule only where it decides an emitted word": a `via` tag sits only on a word whose content its rule chose. `LAY-FALLTHROUGH` therefore tags the first word of the block that is reached by falling through. It used to tag an unrelated word. New independent programs: `within`, `weigh`, `nibble` (the second user of `dis`).
- **G5.** Every hint (the `pdp1.h` macros and `register`) outside comments is deleted in turn, and the copy is compiled. Unchanged Macro text fails the gate. A compile error counts as a change. `SYM` is the exception, since deleting it always renames a label and the deletion test can never flag it. A `SYM` passes only while the source lines that no `lift.toml` region covers, Macro comments removed, still name the symbol it pins. The check found `SYM("dvd")`: every use of `dvd` is inside the divide region. The pin is gone, and divide has a generated symbol. The reference checks now read routine and entry-word addresses from the listing of the last `pdp1cc build`, which names generated symbols too. They refuse a listing whose image does not match the oracle or that is older than the lifted C.
- **G6.** Edits are derived from the C AST: swap the operands of a commutative `+ & | ^` whose operands are memory words or constants, add 1 to a value constant, or add 1 to a shift or rotate count. The gate predicts the rewrite from the rule tables, written out in `gate/predict.py`, and requires the output to equal the original with exactly that rewrite, once per unrolled copy. In an XCT function, a count edit that needs a second word is predicted to be refused. Planted defects (constant-first canonicalization, a load that drops a bit) fail it. G6 covers only those three edits: operand swap, constant + 1 and shift count + 1. It makes no control-flow, `SYM` or layout edits.
- **G3.** `check-g3.py` subtracts the symbols macro1 predefines from the oracle's symbol table before it lints the compiler for Spacewar symbols. Spacewar redefines two of them, `clc` and `ioh` (lines 5-6), so they appear in the oracle's table. They are machine mnemonics that `macro.py` must list to refuse them as `SYM` text, not memorized Spacewar output.

New rules, each with two corpus programs that mirror no lifted routine:
- `XCT-CALL`, `XCT-BODY`. `xct f` with the arguments in AC and IO. The function is the one word its body lowers to; more is an error (`xcttable`, `settle`).
- `JSP-CALL`, `JSP-PROLOGUE`, `JSP-FORWARD`. `jsp f` passes a register argument in IO. The prologue is `dap R`. A JSP function whose whole body is `return g(...)` for a JSP `g` is `jmp g`, because AC still holds the caller's return address. A JSP function cannot take an AC parameter (`jspfold`, `jsplog`).
- `LAY-AT`. `AT(a)` on a definition emits `a/` before it (`xcttable`, `settle`).
- `ST-RESERVE`. A `RESERVE` object (a word, a word array or a pointer) is `. n/`, not punched (`settle`, `route`, `toggle`).
- `EX-CODE`. A function's name as a value is `law f` (`route`, `toggle`).
- `TAIL-CALL-INDIRECT`. `return p(...)` through a pointer to a function type declared with `typedef ... BLOCK;` is `jmp i p` (`route`, `toggle`).
- `EX-HW`. `tyi()` and `lsm()` (`route`, `toggle`).

Deviations from the design, and why:
- **`MINUS_ZERO` is `-(word)0`.** C reads `-0` as +0, so the design's "a negative constant -n is the ones' complement of n" gives +0 for n = 0. A cast to `word` makes the operators the machine's in both readers. `ddd` is `MINUS_ZERO`.
- **The sequence-break save words are lifted code.** The original only sets `3/`. The C reserves words 0-2 at `AT(0)` as `break_ac`, `break_pc` and `break_io`, so `sbf`'s `lac 0`, `lio 2` and `jmp i 1` name what the hardware saved. `0/` and three reserved words set no punched word, so the tape is unchanged.
- **The start vectors carry no `AT(3)`.** They follow the three reserved words, so `AT(3)` would be decoration, and G5 would fail it. The constants table follows at 6 without origins for the same reason.
- **A function-type typedef takes its convention at the end** (`typedef void resume_point(word ac, register word io) BLOCK;`). pycparserext drops an attribute before a typedef's type.
- **Indirect calls are jumps only.** `return p(...)` is implemented, and a call through a pointer that returns is an error. M6's `jsp i \cwg` needs the returning form.
- **A jump through a pointer does not patch an exit.** The caller cannot know the target's exit cell. Each target returns through a BLOCK whose exit the caller adopts by also tail-calling it directly (corpus `route`, `toggle`), or it never returns (`sbf` resumes the interrupted program).
- **XCT and JSP calls clobber AC and IO** in TRACK. No callee summaries yet.
- **The reference build stubs unlifted functions.** `tunables.c` names `a40`, `a1` and `mg1`, which are still Macro. For each function the linked files declare and none defines, the build generates a definition that calls `abort()`. Any other unresolved symbol, such as an extern data word, fails the link.
- **The prelude stays.** Every macro in lines 1-61 and 118-187 that anything uses is used by unlifted code. `senseswitch`, `initialize`, `listen`, `move` and `xincr` have no users, emit no words, and go with the prelude in M7.

### M3 outline compiler (oc, ocs, the outline tables)

Source lines 398-507 compile from `lift/outline_compiler.c`, and lines 1336-1356 (the needle and wedge outlines, `ot1` and `ot2`, with their five spare words each) compile from `lift/outlines.c`. The `plinst` and `comtab` macros (402-414) were defined inside the region and used only there. They are gone: each use is a C statement. `dispatch` is still defined in the prelude and has no user left; it goes with the prelude in M7. Lifted coverage is 415/2514 words (16.5%).

Runtime code generation is data writing plus a jump, as synthesis.md decided. The compiler writes instruction words built by `insn` constructors (`*code++ = I_LAC(&ship_x);` is `lac (lac \sx1 / dac i oc / idx oc`) and patches the address of two jump templates (`start_over.addr = code;` is `dap ocm`). Nothing in the C, the header or the reference build executes generated code. `tools/check-outline-reference.py` runs oc in SIMH from the oracle `.rim` on ot1, ot2 and seven synthetic tables. The tables use every direction code in every position of a word, and reach the 7 code as the first, a middle and the last code of a word, after a store (flag 6 left set) and after a restore. After each call it compares the returned end of the code (the extent), all 01000 words of the code area, the two templates, the entry word, the home instruction of the outline pointer, the pool variables and the program flags with the native build. All 9 tables match. With `I_SUB` encoded as `add` in the native header, all 9 differ.

New rules, each used by two or more corpus programs that mirror no lifted routine (`opcompile`, `copytable`, `bucketlog`). The counts are words of the lifted C.
- `ST-POOL` (34). A `POOL` object is a `\x` variable. Every reference, including one inside a literal (`(lac \sx1`), is written with `\`, so macro1 allocates pool words in first-appearance order. An uninitialized file-scope object without POOL, RESERVE, HOMED or `extern` is an error, so deleting POOL changes the output. `extern POOL` declares one defined in another file.
- `EX-INSN` (41). `I_LAC(&x)`, `I_JMP(f)`, `I_STF(n)`, `I_RCL(n)`, `I_CMA`, `I_IOH`, `I_DPY_NOWAIT` and the rest build one instruction word. It is a constant: a literal when loaded (`lac (add \ssn`), a data word when it initializes a placed word (`insn start_over = I_JMP(&start_over);` is `jmp start_over`). Natively each constructor encodes the word from the opcode and the object's address (below).
- `EX-POSTINC-STORE` (72). `*p++ = e` for a pointer held in a memory word: `dac i p` (or `dio i p` when e is a register local), then `idx p`. AC then holds p. The store can change any word, so TRACK keeps only its facts about register locals.
- `EX-STORE-ADDR` (3). `x.addr = e`, and `p = e` for a HOMED p: e into AC, `dap x`.
- `INLINE-READ` (1) and `JDA-INLINE-ARG` (0). An `INLINE` parameter is the constant word after the call (`jda oc / ot1`). The callee reads it with `lac i R` through its exit cell and returns through `R, jmp .` once `idx R` has stepped past it. The caller writes the constant, an array's name or a function's name as that word.
- `SWITCH` (10). `switch ((int)w)` with cases 0..n in order and no default is `add (T / dap J / J, jmp . / T:` and one slot per case. A case before the last is `goto L` (its slot is `jmp L`) or empty (`opr`, which falls into the next slot). The last case's statements sit in its slot. Values outside 0..n are undefined, as on the machine.
- `HOMED-HOME` (1) and `ST-HOMED` (3). `*home(p)` is p's home instruction, `lac .` or `lio .` under p's label. `p = e` is `dap`, and `++p` is `idx`. Reading p as a value is an error. Exactly one home per pointer: a second definition of the label is a layout error.
- `LAY-PLACE` (2). `PLACE(x, ...)` lays initialized file-scope words out at the statement instead of at their definition. Control must not reach it.
- `EX-FLAG` (3) and `SKIP-FLAG` (1). `stf(n)` and `clf(n)`, and `flag(n)` as a condition: `!flag(n)` skips on `szf n`, `flag(n)` on `szf i n`.
- Extended rules. `EX-CONST-IO` loads a nonzero constant with `lio (c` (the design's table; `cli` stays for 0). `EX-CODE` also covers an array's name and `&object` (`law x`). `ST-PLACED` covers word arrays, whose length must equal their initializer count, and instruction words. `ARGS_DONE()` places `idx R` where the derived placement would not: oc steps its return address after `dap ocm`, and the derived rule would put it before `plinst (stf 5`. Deleting the hint changes the output, so G5 keeps it.
- TRACK callee summaries. A call to a function laid out earlier keeps IO when the callee's words include no instruction that writes IO, no call, no tail call and no adopted or fallthrough exit. Memory facts are dropped, since the callee may store anywhere. This is why `jsp ocs` twice needs no `lio`. Corpus `copytable` fails to compile without it.

Harness changes:
- **Native addresses.** Instruction words and pointers name core addresses, so `pdp1.h` keeps a table of where each C object and function sits. The reference build writes it from the listing of the assembly it compares against (`reference.placements`): the corpus program's own listing, or the last `pdp1cc build` for the oracle checks. `pdp1_address(p)` maps a host pointer to its address, and `pdp1_pointer(a)` maps back for pointer arguments. A null pointer is address 0. A pointer just past an object maps to the address after it, but only when no object contains it. `x.addr` is an anonymous-union view of the word's low 12 bits whose assignment takes a pointer.
- **Pointers.** Parameters, returns, ENTRY_CELL names and POOL objects may be `word *`. The binder rewrites `ENTRY_CELL(f) word *x;` and pointer entry parameters to references to `word *pdp1_cell_f`. Watched words print `pdp1_value(x)`, which is a pointer's address.
- **Generated code that runs.** Corpus `opcompile` compiles a word of 3-bit operation codes into straight-line code and enters it with `return entry(v)` (`jmp i entry`). The native build cannot run that, so the corpus header names a stand-in: `native=run:run_by_hand`. The native build calls `run_by_hand`, which compiles the same code and computes the same result directly, and its entry word stands for `run`'s. Compiling `sub` for the add-one code makes 131 of 320 calls differ.
- **SIMH.** `run_jda` can deposit an INLINE word at call+1 per call, deposit input data once after loading, and examine `PF`.
- **G2** also compares every POOL object and every element of a placed array after each call.
- **G5** now deletes `POOL`, `HOMED`, `INLINE`, `home`, `PLACE(...);` and `ARGS_DONE();`. `RESERVE` was in the pattern with parentheses it never has, so G5 never tested it. It is now a bare hint and earns its place in every file.
- **G6** edits program-flag numbers and `I_RCL`-style counts (`flag` edits): the instruction or literal naming flag n names n + 1, refused past flag 7 (6 for `flag(n)`) or a count of 9. It makes no edits to case labels or array lengths, which are not values.
- **Rejects.** Nine programs: PLACE reachable, a switch with a default or a non-goto case, a homed pointer with two homes or read as a value, `I_RCL(10)`, `ARGS_DONE()` before the inline read, an initialized POOL, and the address of an AC local.

Deviations from the design, and why:
- **`ioh` is emitted as `iot i`.** macro1 has no `ioh`; Spacewar defines it (`ioh=iot i`, line 6), and a corpus program assembles without that line. The word and the literal's value are the same, and macro1 dedups literals by value.
- **The jump templates and generated symbols.** `ocm, jmp .` compiles as `zo10, jmp zo10`: same word. The original labels `ock`, `oco`, `ocq`, `ocp` and `ocr` name nothing any instruction uses, so they are gone.
- **PLACE takes file-scope words, not static locals.** The native address table is written after the lifted files and can only name file-scope objects.
- **ENTRY_CELL may share its owner's parameter name.** oc's entry word is `code` in both `outline_compiler` (its parameter) and `compile_twice` (the ENTRY_CELL name), since both name one cell.
- **`switch ((int)w)`.** The native `word` converts to `int` only explicitly; an implicit conversion would make `w + 1` ambiguous against the built-in `+`.
- **HOMED and the switch arrive before M5 and M7.** oc needs both (`ocg, lio .` and `dispatch`). Only the forms oc and the corpus use are implemented.
- **The ship variables are declared in `outline_compiler.c`.** oc's text is their first appearance, so it decides their addresses. They keep their Macro names by SYM because the unlifted spaceship code names them. M6 will declare them `extern POOL` where it needs them.
- **Label merging.** When a home instruction is also a C label or loop top, the first label names the word and the others are renamed to it. A pinned homed pointer could lose its symbol this way; the build's interface check would then fail.

### M4 heavens (the central star, the Expensive Planetarium, the star catalog)

Source lines 510-621, 629-653 and 1373-1866 compile from `lift/heavens.c`, one region with three line ranges. Lifted coverage is 1733/2514 words (68.9%); the catalog is 938 of them.

The C forms:
- **The `random` macro** is `static inline word next_random(void)`, laid out at each of its two calls. The macro stays in the prelude for unlifted code.
- **`bpt` and the unrolled `starp` block are Duff's device.** `HOMED word line_dots_skipped;` is the switch index, held in the jump into the line. `line_dots_skipped = skipped;` is `sal 3s / add (bds / dap bjm`, and `switch ((int)line_dots_skipped)` is `bjm, jmp .`. Cases 0-6 each hold one `line_step` and fall into the next; case 7 holds nine. The mirrored second pass is a `for (;;)` around the switch, so its `jmp bjm` re-enters the stored case. `starp` is `static inline dword line_step(word x, register word y)`; its two swaps are `rcl(x, y, 18)`, since both halves are live.
- **`dislis` x4 is a cpp macro that defines functions.** `MAGNITUDE(m, stars, count, intensity)` defines, for one magnitude, two HOMED star pointers (`fin`, `fyn`), the cursor and scan-start words (`flo`, `fpo`), and `static inline void display_magnitude_m(void)`. `bck` calls the four functions in order. A static inline function with `int` parameters would share one set of state words in the native build, since C has one static per function; the machine has a set per copy. One function per magnitude, called once, keeps the two in step. The state words are file-scope objects that the function PLACEs at its end, where `dislis` has `fpo` and `flo`.
- **The cross-instance jumps.** `jmp flo+R+1` is the word after a `dislis` copy, which is the first word of the next copy (or `isp bkc` after the fourth). It is a return from the static inline function: a return before the function's last statement jumps to the word after the copy (INLINE-RETURN). No C names another copy's words. The C has one `done: return;`, at `fx`; the other exits are `goto done`, as the source's are `jmp fx`.
- **`bck`'s exit cell** sits under `isp bcc`, in the middle of the routine. The source-last return owns the exit cell, so the C writes `if (++alternate_frames < 0) finished: return;` and the later exits are `goto finished`.
- **The catalog** is four `word` arrays, one per magnitude, of `STAR(x, y)` pairs with each star's name from the source comment. `STAR(x, y)` is `8192 - (x), (y) * 256`, decimal as in the source, folded by C's rules. `AT(06077)` places the first table.

New rules, each used by two or more independent corpus programs (lift words in parentheses):
- `INLINE-CALL` (322), `INLINE-RETURN` (4). A call of a static inline function lays its body out at the call with fresh labels (dotline, lookup, ringscan). Its parameters take the caller's AC and IO; TRACK carries memory facts in and out.
- `SWITCH-HOMED` (4). Duff's device (dotline, ticks). Each case before the last is a power of two of words; the store scales the index by that shift. The stride is found by lowering the cases, so the function is lowered until the strides, like the label states, are a fixpoint.
- `HOMED-WORD` (4). `I_LIO(p)` and `I_LIO(++p)` for a HOMED p whose home is `lio .` are its home word (`lac fyn`, `idx fyn`) (lookup, ringscan). `sad (lio Q+2` and `sad fpo` compare instruction words, so the C does too: `I_LIO(++star_y) == I_LIO(stars + 2 * (count))`. The design's EX-HOMED-CMP compared a pointer with a constant pointer; `fpo` is an instruction word, not a pointer, so the instruction form covers both comparisons.
- `SKIP-SAME` (16). `a == m` and `a != m` with m a word or constant skip on `sas` / `sad` (lookup, ringscan). Other orderings against a nonzero value are an error.
- `SKIP-SENSE` (2). `sense(n)` (dotline, ticks).
- `EX-DPY` (21). `dpy(x, y, n)` is `dpy-i+n00` and `dpy_nowait(x, y)` is `dpy-4000`, with x in AC and y in IO, both kept (dotline, ringscan, ticks). `ioh()` is `iot i` under `EX-HW`.
- `OPR-COMBINE` (1). A comma statement whose parts are each one operate-group instruction, writing different registers or the flags, is one word: `pen.hi = 0, pen.lo = 0, clf(6);` is `cla cli clf 6-opr-opr` (dotline, ticks). Parts that write one register are an error, since the result would depend on the hardware's order.
- Extended rules. `ST-PLACED` covers a pointer word initialized with an address (`flo, 4j`). A HOMED pointer may be initialized, which sets its home's address field (`fin, lac` is `= 0`). `x.addr = e` and `p = e` emit only `dap` when TRACK knows AC's address field already holds e (`dap fpo / dap fin / dap fyn`, and `dap fin` after `lac (lio J`). Address operands may be `array + n`. Constant expressions of `+ - * << >>` fold as C folds them.

Harness:
- **The display, compared.** SIMH has no display, so the harness sets a breakpoint on every display instruction that examines AC and IO and continues; the native `pdp1.h` records each point it is asked to plot. G2 and the reference checks compare the points, in order, call by call. The simulator's I/O synchronizer is set, so `ioh` never waits. Sense switches vary per corpus call.
- **`tools/check-heavens-reference.py`** compares the 938 catalog words of the native tables with the words SIMH loads from the oracle image at 06077 (all match), 100,000 calls of `blp` from four seeds of `ran` (random number, `bx`, `by`, the `bjm` jump word and every plotted point after each), 263,144 frames of `bck` in a row, which take the window once round the sky (8192 right margins), and 20,000 frames that each start from a random right margin. After each frame it compares the counters, the right margin, and each magnitude's cursor, scan start and both home words, plus every plotted point. All match: 7,972,764 points from `bck`.
- **The SIMH stub moved** from 07700 to 07760. At 07700 it overwrote catalog words 07700-07712, which the random-margin frames read. The moved stub is above the catalog's last word (07750).
- **Labels.** Several labels may name one word (`a, b, lac .`); none is renamed. M3 merged them into the first, which lost a HOMED pointer's symbol when a C label named its home.
- **One past the end.** A native pointer one past an array's end can coincide with the next host object, and `pdp1_address` then names that object. The heavens check reckons the star pointers' home words from their table. G6 now predicts folded constants, array offsets, sense and intensity fields, refuses count edits that lengthen a Duff case, counts copies of static inline code, and accepts an edit when the output is the original with exactly that many predicted rewrites. It runs its edits in parallel.
- `-Wno-array-bounds` in the native builds: g++ warns that a home pointer initialized to null may be read, which the C never does.

Deviations from the design, and why:
- **No `int` parameters on static inline functions.** The design's ST-CT form for `dislis` needs per-copy state, which C statics cannot give natively (above). A cpp macro defines one function per magnitude instead.
- **`and (add 340` is written as 0400340** (`SLOPE_BITS`). It is a mask, not an instruction; macro1 dedups literals by value.
- **The `starp`, `dislis` and `mark` macro definitions are gone**, since every use was inside the region. The `background` macro (lines 624-627) stays as source text, because the unlifted main loop uses it; that is why the region has three ranges. The unused label `fs` is gone. `blp`, `bck`, `bx`, `by` and `ran` keep their symbols by SYM; unlifted text names them.
- **The catalog title line (1371) and the `start` lines stay.** They emit no words.


### M5 objects (explosion, torpedo, hyperspace, spaceship in star)

Source lines 946-1077 and 1312-1333 compile from `lift/objects.c`, one region with two line ranges. Lifted coverage is 1908/2514 words (75.9%). `lift/object_table.h` declares the object table's cursors, and `lift/random.h` now holds the `random` macro that heavens and objects share.

The C forms:
- **The cursors.** A calc routine works on the current object through the main loop's cursors: `*x_slot`, `++*counter_slot`, `*routine_slot = 0`. `*p` is `op i p` whether p is a pool word (`\mdx`) or the address field of an instruction (`mx1, lac .`). The header declares each cursor `extern` with its symbol pinned; M7 defines them, with their homes, without changing this C.
- **The `diff` macro** is `static inline word move_x(word acceleration)` and `move_y`, laid out at each of four calls. The macro's scaling is an instruction run from a constant, so the C writes `xct(I_SAR(3), dx)`, which is `xct (sar 3s`.
- **mex's runtime-built shift** is `HOMED insn particle_shift = I_HLT;`. The particle loop stores `(next_random() & 0777) | I_SCL(0)` into it (`and (777 / ior (scl / dac mi1`), and `xct(particle_shift, hi, lo)` is the word itself, `mi1, hlt`, run where it stands.
- **`msh, xct .`** is `HOMED const insn *spread_scale` into `insn spread_scales[2] = { I_SCR(1), I_SCR(3) }` (`mst`). `spread_scale = spread_scales` is `law mst / dap msh`, `++spread_scale` is `idx msh`, and `xct(*home(spread_scale), hi, lo)` is the home `msh, xct .`. The C comments the masswerk bug: the count is negative, so the wider spread is never picked.
- **`lac (mex 400000`** is `explosion | NON_COLLIDING`, one literal `(mex+400000`.
- **`count i ma1, X`** is `if (++*counter_slot < 0) goto X;` (`isp i ma1 / jmp X`). `setup \hpt,3` is `angle_steps = -3`. `dispt i, i my1, n` is `register word y = *y_slot; dpy(x, y, n);`. `cma cli-opr` is `count = -count, spot.lo = 0;`. The `swap` macro is `rcl(h, l, 18)`.
- **pof** is a BLOCK entered by `jmp pof` whose returns are `return spaceship_done();`, a tail call of `srt`. M6 can define `srt` as a BLOCK whose exit `ss1` and `ss2` adopt.
- **hp1 reads IO** at entry: `scr 9s` shifts the main loop's IO out. The C takes it as `register word io`.

New rules, each used by two corpus programs that mirror no lifted routine (lift words in parentheses):
- `EX-DEREF` (61). `*p` names p's cell with the indirect bit: `lac i`, `add i`, `dac i`, `dzm i`, `dio i`, `lio i`, `isp i`, `idx i` (meters, exchange). A store through a pointer can change any word, so TRACK keeps only register facts after it.
- `EX-XCT` (6). `xct(w, a)` and `xct(w, hi, lo)` run an instruction word: `xct (w` for a constant, `p, xct .` for `*home(p)`, or the HOMED insn itself (sparkle, stepper, blur). The compiler refuses a constant outside the shift group, and in `xct(w, a)` one that shifts IO; TRACK keeps IO only across a constant shift of AC, since a word built at run time may shift IO (the native `xct(w, a)` aborts if it does).
- `ST-HOMED-INSN` (2). A HOMED insn is the instruction at its home, its one `xct`, laid out there with its initializer; `x = e` is `dac x` (sparkle, stepper, blur). One with no home, two homes or no initializer is an error.

Extended rules, each used by two corpus programs: `I_SCL`, `I_SCR`, `I_SAR` and `I_HLT`, with count 0 as the bare mnemonic (`ior (scl`); `sil`/`sir` for `io = io << n` on a register local (`EX-SHIFT`; blur, exchange, sparkle); `f | (word)c` with c above the address field (`EX-CODE`; meters, blur). `++*p;` as a statement leaves the new word in AC, so TRACK forgets AC there (reject `deref-inc-ac`). TRACK carries the caller's register locals through a static inline body that leaves that register alone; sparkle fails to compile without it.

Harness:
- **`tools/check-objects-reference.py`** runs each routine 10,000 times from seeded random objects, plus edge states (counters at -1, -0, 0, +1 and the extremes; jumps left at -1, -0, 0; uncertainty at 0, 0340000, 0377777, 0400000). Each call picks a slot (a ship's for hp1, hp3 and pof), points every cursor at it in SIMH (the cursors' instruction words and pool words) and natively (C pointers into a table laid out as the machine's), and fills the slot. After each call it compares all 188 table words, `ran`, `\mxc`, `\hpt`, `\ssn`, for mex the `msh` and `mi1` words, and every plotted point: 50,072 calls, 0 differ, 664,234 points. pof runs from `jmp pof` with `srt` patched to return. Counting a shift's bits wrong in the native `xct` makes 9,956 of 10,019 explosion calls differ.
- **The native `xct`** gives the shift group a meaning: it reads the kind and counts the bits set in the low nine, as the machine does, and calls the same `rcl`, `scl`, `sar` and the rest as the lifted C. Any other word, a halt among them, aborts.
- **G5** checks headers: a hint deleted in a header must change the output of a file that includes it. A SYM also passes when another lifted file pins the same symbol: `the`, `hd2`, `hd3`, `hr1`, `hr2` and `hur` now link `tunables.c` to `objects.c` and no unlifted text names them. G6 predicts `sir` counts and `I_SCL`-style fields, count 0 included.
- **macro1 reads an unseen symbol as a pseudo-op** that shares its first three characters (`\state` assembled as `start`). `macro.predefined` refuses those prefixes.
- The reference build takes `-iquote` for each lifted file's directory, and `bodies` for unlifted functions the lifted code calls (`srt` returns).

Deviations from the design, and why:
- **The cursors are `extern` without HOMED.** Through an extern pointer and through a homed one, `*p` is the same word, `op i p`. G5 flags HOMED there as decoration. The storage class belongs to the definition, as in C; M7's definitions carry HOMED.
- **The slot is a HOMED insn, not `SLOT dword mi1(dword)`.** HOMED already means "storage in the instruction at its home"; for an `insn` the storage is the whole word. A C function cannot be assigned, so a slot spelled as a function would need a new kind of object.
- **The native header executes shift instructions.** The playbook says the reference build never executes generated code, and mex runs a shift it builds at run time. The M5 brief allows exactly this form: a shift word run by `xct` whose C meaning the header defines. It decodes one instruction group into the same `rcl`, `scl`, `sar` and the rest the lifted C calls; any other word aborts, and the compiler refuses `xct` of a constant outside the group. Code the outline compiler generates and enters by a jump is still never run natively. The operator should confirm this reading.
- **pof's busy wait is a label and a goto.** `while (c);` is not implemented; M7's `count \mtc, .` will want it.

### Typed shifts (after M5)

The operator ruled out the M5 native `xct`, which decoded encoded instruction words: pdp1.h holds no interpreter. A shift is now a value of its own type, and the emitted Macro is unchanged (every lifted file and corpus program lowers byte-identical).

- **`shift`** is the type of a shift instruction. `I_RAL`, `I_RCL`, `I_SCL`, `I_SAR` and `I_SCR` return one. `I_SCL_BITS(w & m)`, with m a constant within 0777, is `scl` by as many places as `w & m` has bits set; it lowers to `w & m` then `ior (scl`, the words the old `(w & 0777) | I_SCL(0)` gave. `SHIFT_UNSET` replaces `I_HLT` as the `hlt` a shift slot holds before the program first builds its shift.
- **Executable slots are shifts.** `HOMED shift x` replaces `HOMED insn x`, and `xct(*home(p), ...)` needs p to be a `const shift *`. The compiler refuses a store of anything but a shift into a shift, a shift array or through a pointer to a shift, a pointer to a shift that is not given the address of a shift, a shift function that returns a word, and an `_BITS` argument that is not `w & m` with m within 0777 (rejects `shift-*`, `xct-word-pointer`). A shift stored where an `insn` is wanted is its instruction word, as the outline compiler's `I_RCL(9)` is.
- **The native build** holds a shift as `{kind, count bits}`. `xct` switches on the kind and calls the same `ral`, `rcl`, `scl`, `sar` and `scr` the lifted C calls, with the count the number of bits set in the count field the constructor stored. `SHIFT_UNSET` aborts. Encoding a shift into a word is construction only: the watched `mi1` word and the outline compiler's stored `rcl 9s` need it. Nothing decodes a word.
- **macro1's predefined names** are read from `tools/macro1.c`'s `pseudos` and `permanent_symbols` tables, not a hand-copied list. Reject `sym-pseudo-prefix` covers a symbol refused only for its three-letter pseudo-op prefix.

### M6 spaceship (ss1, ss2 through srt, and pof)

Source lines 1079-1333 compile from `lift/spaceship.c`, one region. It takes pof (1312-1333) over from the objects region, which is now 946-1077: see the deviations. Lifted coverage is 2168/2514 words (86.2%). `lift/inertia.h` now holds `move_x` and `move_y` (the `diff` macro), which objects and the spaceship share.

The C forms:
- **The routine is four BLOCK-chained functions.** `first_spaceship` (ss1) and `second_spaceship` (ss2) are JSP entries that read the control word and tail-call `spaceship` (sr0); ss2 falls into it. `spaceship` ends `return (*home(draw_outline))();`, the jump into the compiled outline, or `return spaceship_in_star();` (pof). `outline_drawn` (sq6) is where the compiled outline jumps back; it ends in `spaceship_done` (srt), an empty BLOCK whose `jmp .` is the routine's exit.
- **`jsp i \cwg`** is a call through a POOL pointer to a JSP function type: `dword c = get_control_word();` with `typedef dword control_word_getter(void) JSP;`. The control word comes back in IO, as `mg1` leaves it.
- **Entering the compiled outline.** `draw_outline` is `HOMED compiled_outline *`, a pointer to a BLOCK function type whose home is the jump `sp5, jmp .`. `(*home(draw_outline))()` is that jump, as `*home(p)` is the home instruction for a data pointer. The main loop's `dap sp5` stores the address. Natively the jump is a call through a function pointer; nothing in the native build points it at generated code (see Harness).
- **The divide's caller (`jda idv / lac \t1 / opr`).** `SKIPS` on a JDA function, or on the BLOCK it tail-calls, says the call may return one word further (`skip_return()`). A call of a SKIPS function is followed by its slot, `opr`, which runs only when the call does not skip. The C is a plain call, `q = integer_divide(-*x_slot, f.lo, work);`, and means the same either way: on overflow idv returns |divisor| with the quotient's sign, and the slot does nothing. A caller that must act on the skip has no form yet; nothing needs one.
- **Homes that are not loads.** `mom, add .` and `mth, add .` are `turn + *home(angular_momentum_slot)`. The torpedo launch fills the new object's slots through pointers homed in the stores: `*home(torpedo_x_slot) = start;` is `ss3, dio .`, `*home(torpedo_dx_slot) = ...;` is `sr3, dac .`, and `home(torpedo_cycles_slot)->addr = 020;` is `sr7, dap .`.
- **Pointers built from a homed pointer.** `torpedo_x_slot = NOB + free_slot;` is `law nob / add sr1 / dap ss3`: the add reads sr1's whole home word, `lac` and the pointer, and the dap keeps only the address. Each next slot is the previous plus NOB, `add (nob / dap`, with no reload: after a dap, AC's address field is the stored pointer.
- **The free-slot search** is the `index` form of M4 (`I_LAC(++free_slot) != I_LAC(object_table + NOB)`), and `hlt / jmp .-1` when the table is full is `for (;;) hlt();`.
- **`lac (tcr`** is `torpedo | COLLIDING` with `COLLIDING` `(word)0`: a routine word, like `explosion | NON_COLLIDING`, loaded from a literal. A bare function name stays `law f`.
- **`cla / sad i \mfu / clf 6`** is `if (0 == *fuel_slot) clf(THRUST_FLAG);`; `clc` is `fire = MINUS_ZERO;`.
- **Cursors.** `angular_momentum_slot` (mom), `angle_slot` (mth) and `previous_control_slot` (mco) are defined here, since their homes are in this routine; `object_table.h` declares them extern HOMED (since the M7 merge). `fuel_slot` (mfu), `torpedoes_slot` (mtr) and `object_table` (mtb) are new declarations there.

New rules, each used by two corpus programs that mirror no lifted routine (`relay`, `beacon`, `garage`; lift words in parentheses):
- `CALL-INDIRECT` (2). `p(...)` through a pointer word to a JSP function type is `jsp i p`, and returns (relay, beacon).
- `SKIP-SLOT` (2). The `opr` after a call of a SKIPS function (relay, beacon).
- `HOMED-VALUE` (1). A HOMED pointer read in the value a dap stores: `add p` / `lac p`, or nothing when AC's address field holds it (relay, garage). Anywhere else a homed pointer's value is still an error.

Extended rules, each used by two of those programs: `HOMED-HOME` for `add .`, `dac .`, `dio .`, `dap .` and `jmp .` homes; `LAY-ADOPT` through a chain of BLOCKs (`relay -> route -> finish`, `beacon -> choose -> off`); `EX-CONST-AC` gives `clc` for -0 (garage, relay, beacon); `EX-HW` gives `hlt` (garage, beacon); `SKIP-SAME` against `*p`, `sad i p` (relay, garage, beacon); `EX-CODE` loads `f | c` from a literal even when c is 0 (garage, beacon); POOL and HOMED pointers to function types; HOMED on a definition whose extern declaration omits it (relay, garage). TRACK keeps the address-field fact of a homed pointer across a store through a pointer, since a C pointer cannot reach a home.

Harness:
- **`tools/check-spaceship-reference.py`** runs the routine in two halves, because the native build cannot run the compiled outline. ss1 and ss2 run from `jsp` to the jump into the outline: SIMH has `sp5` jump to the stub's second halt, and natively `draw_outline` points to a stand-in that only records it was entered, so both report the same return point. Their other exit is pof, back through `srt` as their own `dap srt` set it. `outline_drawn` runs from `jmp sq6` with the pool words the first half and the outline leave (control word, heading sine and cosine, pen position, torpedo start) set at random, and `srt` patched to return; pof runs from `jmp pof` the same way. `\cwg` names a three-word routine in free core that loads a deposited control word into IO; natively `get_control_word` points to a function that returns it. Each call fills a ship's slot, every object's routine word (some free, at least one), the random number and the sense switches, points every cursor at the slot and the launch pointers' homes at the table. After each call it compares the 188 table words, `ran`, every pool word of the routine (20, with `bx` and `by`), the program flags, the launch pointers' home words, the return point and every plotted point. 32,500 calls, 0 differ. With a wrong address bit planted in the native `x.addr = n` and a wrong `ral 7s` count, 6,975 of 9,750 calls differ.
- **What the hash alone covers.** The compiled outline's code (generated by oc, whose writing M3's check covers word by word) and the jump into it run only on the machine. The reference halves meet at `sp5` and `sq6`; the words of both, and of every instruction in the region, are fixed by the hash. The full-table path, `hlt / jmp .-1`, is not run: SIMH would stop there.
- **Skips belong to a call.** The native `skip_return()` counted into one global, so a skip inside a nested call leaked into its caller's return point. The reference build now opens every definition that is not SKIPS with `pdp1_skip_guard`, which restores the count when it returns. Corpus `relay` differs from SIMH on 319 of 320 calls without the guard.
- **G6** reads pool operands with their `\` and treats extern arrays as arrays; both were missed before (relay, and `object_table + NOB`).

Deviations from the design, and why:
- **pof moved into the spaceship region.** ss1's `dap srt` patches the exit of the routine it tail-calls. The compiler finds that exit by following tail calls through BLOCKs it can see: `spaceship` reaches `srt` only through pof. With pof in another file, the chain stops there. pof is the routine's star-capture path in the source too (it ends `jmp srt`).
- **`srt` and `pof` lost their SYMs**, since nothing outside this file names them now. `sq6` stays pinned: oc's compiled code jumps to it from another file.
- **`*a` for an array a is now an error.** It compiled to `op i a`, through the word a[0] holds, where C means a[0]. No lifted file used it; corpus `beacon` found it.
- **The labels `trf`, `sp1`, `sp2`, `sr0`/`sc1`, `st3` and the rest** name nothing outside the region; they are C labels or function entries with generated symbols.
- **The native `x.addr = e`** takes an integer or a word, as well as a pointer: `home(torpedo_cycles_slot)->addr = 020`.

### M7 main loop (the frame, the object loop, game control, core layout)

Source lines 664-941 and 1357-1366 compile from `lift/main_loop.c`, one region with two line ranges. A `[[dropped]]` entry in `lift.toml` leaves out the macro definitions and equates whose users are all lifted: after M6, every macro of the prelude (`szm` .. `ranct`, lines 3-60 and 117-189), `background` (622-628) and `nob` (663). They make no words, and the hash shows it. Lifted coverage is 2514/2514 words (100%). It counts the 84 literal constants, which a compiled `CONSTANTS()` places. The source lines left are titles, `start` directives, comments and blanks.

The C forms:
- **The object table** is one `RESERVE` array, `object_table` (`mtb`), of 0274 words, after `CONSTANTS()`, `VARIABLES()` and the patch space (`p, . 200/`). Each property is a macro naming where its array starts (`X_POSITIONS` is `object_table + NOB`), and `X_POSITIONS[1]` is the word `mtb+31` (EX-ELEMENT). The equates `nx1` .. `nnn` are not symbols any more; their words are the same addresses.
- **The cursor setup at ml0** walks an AC local `word *slot` from property to property (`slot = slot + NOB` is `add (30`) and stores each cursor: `dap` for a homed one, `dac` for a pool word.
- **The cursors' homes.** `routine_slot`, `x_slot`, `y_slot`, `cycles_slot` and `outline_slot` are `lac .` homes, `counter_slot` is a `dac .` home. The other object's cursors are `lac .` (`ml2`), `sub .` (`mx2`, `my2`), `add .` (`mb2`) and `dac .` (`ma2`). `object_table.h` now says HOMED on the cursors that are instruction fields; `angular_momentum_slot`, `angle_slot` and `previous_control_slot` have their homes in the spaceship routine, which defines them. The main loop stores the compiled outline's address through `extern HOMED compiled_outline *draw_outline` (`mot, lac . / dap sp5`), a cast of the outline word to M6's BLOCK function type.
- **`law 1 / add ml1 / dap ml2`** is `other_routine_slot = 1 + routine_slot` (HOMED-VALUE).
- **The calc routine call** `lac i ml1 / dap . 1 / jsp .` is `((calc_routine *)*routine_slot)()` (CALL-COMPUTED). The `dap` keeps the address bits, so the non-colliding sign bit drops out, as in C's cast.
- **The collision test** keeps |dx| in a pool word (`\mt1`) and clips the square's corners with |dx| + |dy|. The explosion trigger stores one AC local through both routine cursors.
- **The spare-time loop** `count \mtc, .` is `spare: if (++spare_time < 0) goto spare;`.
- **Game control.** `a1`, `a40`, `a`, `a6` and `a2` are BLOCKs; `a` falls into `a6`, and `a6` into `a2`. `next_frame` (ml0) tail-calls the object loop or `between_games`, so a BLOCK may now tail-call several BLOCKs. The `clear` macro is a HOMED pointer whose home is `dzm 0`, and its bound is `I_DZM(...)`. The scores show by `halt(first, second)`.
- **The control word getters** `mg1` and `mg2` are JSP functions returning an `io_word`. `tunables.c` declares `mg1` and `cwr` the same way now (they were `dword` with no parameter; the words are the same).

New rules, each used by two or more corpus programs that mirror no lifted routine (lift words in parentheses):
- `EX-ELEMENT` (23). `a[k]` for a file-scope array, or an address `a + n` into one, and a constant k (ledger, signal, tasks).
- `HOMED-VALUE`. M6 landed the same rule in parallel; the merge keeps M6's form, a HOMED pointer read in the value a dap stores, which covers `n + p` and `p + n` (ledger, signal, tasks, with M6's relay and garage). Any other use of the value is an error (rejects `homed-value-stored`, `homed-value-added`).
- `CALL-COMPUTED` (4). `((f *)e)()` for a JSP function type f with no parameters (signal, tasks). A function type returning an `io_word` leaves the result in IO.
- `SKIPNOT` (1). `SKIPNOT(c)` for a sign test of AC: `spa i` where the default is `sma` (ledger, tasks).
- `SWAP` (2). `SWAP(x)`: a move between AC and IO by `rcl 9s` twice (signal, tasks).
- `LAY-POOL` (2). `CONSTANTS()` and `VARIABLES()` (ledger, signal, tasks). The corpus harness no longer appends its own `constants` and `variables` to a program that places them.

Extended rules: `HOMED-HOME` covers `dac .`, `dzm .` and `dio .` homes as stores and `add .` and `sub .` homes as operands (ledger, signal, tasks); `EX-INSN` and `HOMED-WORD` cover `I_DZM` (ledger, tasks); `EX-HW` covers `lat()` and `halt(ac, io)` (signal, tasks) and `control_boxes()`, `iot 11`, which no corpus program runs (below). A HOMED pointer defined in a file must have its home there (reject `homed-pointer-no-home`), and a function cannot adopt the exit of a BLOCK that tail-calls several BLOCKs (reject `adopt-exitless`).

Harness:
- **Test word and halts.** Each corpus call sets the test word (`dep TW` in SIMH, `pdp1_test_word` natively). A compiled `hlt` gets a SIMH breakpoint that reads AC and IO and steps past it; the native `halt` records the same pair, and both go into the plotted points that G2 compares. Recording the native pair in the wrong order makes 193 of 320 signal calls and 320 of 320 tasks calls differ.
- **Computed calls natively.** `(f *)w` converts a word to the function at its address field through the address table, which now marks functions. `word * + word` adds as `law p / add w` does.
- **G5** also checks `SKIPNOT`, `SWAP`, `CONSTANTS()` and `VARIABLES()`. A SYM in a header earns its place when two files that include it use the name it declares (`mh4` links objects.c and main_loop.c).
- **G6** predicts edits to the constants of an array address chain or a subscript (`mtb+256`), and spells a pool operand with `\`.
- **The objects and spaceship checks** read the table's equates (`nx1` .. `nnn`) from the oracle listing; the build no longer defines them. The spaceship check defines natively only the HOMED cursors whose homes are not in spaceship.c. It defines the header's pool cursors that no calc routine uses.
- **The interface check** removes Macro comments before it looks for a symbol in unlifted text (it found `a` in comments).
- **Lifted coverage** counts the words a listing line makes after its first under that line: the literal constants under a compiled `CONSTANTS()` count as compiled.

Deviations from the design, and why:
- **`nob=30` (line 663) is dropped** now that ss1/ss2 are lifted; nothing unlifted names it.
- **One array for the table, not one per property.** The cursor setup steps from one property's array to the next by adding NOB. Across separate C arrays that is undefined; inside one array it is plain pointer arithmetic.
- **The cursors are HOMED in `object_table.h`.** M5 left HOMED off the extern declarations because no file defined a home. All declarations of an object now agree with the definition, and a `p = e` in a file without the home must still be a `dap`.
- **`control_boxes()` has no SIMH run.** The headless simulator stops on `iot 11`; only the hash covers that word. The frame-level check below starts the game at 5 (test word), so mg1 does not run there either.
- **The main loop has no native reference.** Through ss1/ss2 it enters the compiled outlines (generated code), which the native build cannot run.

**Merging with M6.** M6 and M7 were built in parallel. Where both extended the compiler, the merge keeps one rule with one meaning:
- `*home(p) = e` lowers through M6's `HomeStore` alone, with M7's `dzm .` home for 0 and M7's check that the store matches p's home instruction (reject `home-op-mismatch`).
- `LAY-ADOPT` follows M6's chain of BLOCKs to the exit cell, and a function whose chain ends in a BLOCK that tail-calls several BLOCKs still has no exit to adopt (reject `adopt-exitless`).
- `HOMED` on spaceship.c's cursor definitions became redundant once the header says it; G5 flagged it, so the definitions drop it.

**Frame-level check.** `tools/check-main-loop-frames.py` runs SIMH on the oracle image and on the built image in lockstep: 17 scenarios (start at 5 and at 4, sense switches, seeds, `ddd` = 0, tunables that fill the table), ship controls and match switches on the test word from a seeded policy, a stop at every frame seam (ml0) and every halt. At each stop it compares the object table, the scores, the game count, the restart delay, the spare time, `ran`, AC, IO and the flags: 96049 stops, 0 differ. Identical images make that trivial; its value is coverage of the built image, read by self-removing SIMH breakpoints (xct targets counted through their xct). After the merge with M6, 1412 of 1442 compiled code words run (97.9%), main_loop 261/261, spaceship 276/277. The `jmp .-1` after the full-table halt counts as run when the halt repeats after `cont`. The 30 that do not: the sequence-break flush, the outline compiler's direction code 2 (no shipped outline uses it), sin's overflow clamp, dvd's entry (only idv is called), a mex path and pof's wait loop that need a negative instruction count, and some heavens scan-wrap paths, which check-heavens-reference covers. A one-word change to the built image (`maa`) fails at stop 2. It says nothing about what the C means natively.

### M8 the finish line (the program build, review follow-ups)

`pdp1cc build` compiles the files `lift.toml` lists, in that order, into one Macro program and assembles it. No line of `source/spacewar3.1_complete.txt` takes part; the source stays in the repo as the oracle's input. Lifted coverage is 2514/2514 words. `tools/check-g3.py` runs the whole build in a tree without `source/` and `build/` and gets the oracle hash.

**What the residue was.** After M7 the build still spliced into the source text, and the lines left were titles, `start` directives, comments and blanks. Each tape-level fact now has a C form or is shown to make no byte:
- **Titles.** macro1 reads the first line of a tape as its title. The title goes to the listing and to stderr, never to the tape (`processLine` in `tools/macro1.c`; assembling with another title gives the same `.rim`). The compiler frames the program with its own title line, `pdp1cc lift.toml`.
- **`start` with no operand** (source lines 62, 655, 1368). It flushes the loader block and ends a tape segment, and the next line is read as a title. Removing all three, with their titles, leaves the hash unchanged: each falls where the next word starts a new block anyway (an origin change). They have no C form.
- **`start 4`.** It ends the tape with `jmp 4`, the address the loader starts the program at. In C it is `START` on the start vector `start` in `tunables.c`: the BLOCK function the tape starts at.
- **Comments and blanks** make no byte.

New rule:
- `LAY-START`. `START` on a BLOCK function with no parameters ends the program with `start f`. The program emitter puts it last, since macro1 ends a tape at `start`; a second START is an error (rejects `start-twice`, `start-not-block`). Corpus `odometer`, `thermostat` and `console` use it; G2 checks that SIMH's PC after loading the tape is the START function's address.

Extended rule: `CALL-INDIRECT` takes a JSP function type that returns an `io_word`: the result is in IO (corpus `turnstile`, `console`; `spaceship.c`'s control word).

**Linking by C name.** A C name of external linkage is one Macro symbol in every file of the program (`dialect.external_symbols`): a short name is its own symbol, a long one gets a generated `y<n>`, numbered in order of first declaration across the files. A lone file is its own program. `SYM` existed to make spliced C and unlifted text agree on symbols; with no unlifted text, every pin failed G5, so `SYM` is gone from the dialect, `pdp1.h`, `lift/` and the gate (rejects `sym-*` gone). Each definition keeps the original symbol in its comment. Two pins had joined objects that had different C names:
- `\bx`, `\by`: the central star's slope and the spaceship's gravity. One pool pair now, `star_vector_x` and `star_vector_y` in `star_vector.h`; each user names it for its own meaning with a macro.
- `\cwg`: `main_loop.c` declared it a pointer to `io_word f(register word io)`, `spaceship.c` a pointer to `dword f(void)`. `control_word.h` declares the type and the pointer once: `io_word control_word_reader(void) JSP`. The getters take no parameter now; `read_test_word` is `SWAP(lat())` (the same `rcl 9s` pair).

**Declarations agree across files.** The build refuses a function, or an object that points to a function type, declared with different shapes in two files (convention, parameter kinds, return, SKIPS). It found the `\cwg` mismatch when that was put back as a test.

**Files.** `REGION_BREAK` is gone. The star catalog is `lift/star_catalog.c`, the last unit on the tape; the constants, variables, patch space and object table are `lift/core_layout.c`. `NOB`, the table's size and each property's start moved to `object_table.h`, since three files use them.

**Nested SKIPS.** A SKIPS function that called another SKIPS function other than as its tail call leaked the inner skip into its own native skip count: the reference build guards only functions that are not SKIPS. The shape is rejected (`skips-nested`); nothing used it.

**Entering the compiled outline stays a tail call.** The review asked for `(*home(draw_outline))(); return outline_drawn();` so that `outline_drawn` reads as part of one flow. The words would allow it (`jmp .` at the home, and the tail call elided by fallthrough), but the C would claim something the compiler cannot check. A statement call means the callee comes back to the next statement. The compiled outline comes back only because the outline compiler wrote `jmp outline_drawn` into it; a call through a pointer gives a BLOCK no return address and patches no exit. Lowered as a bare jump, the same statement with any compiled BLOCK target would run the continuation twice natively (once inside the callee's own tail call, once after it) and once on the machine. So the entry stays `return (*home(draw_outline))();`, and the return path is stated where it is made: `*code++ = I_JMP(outline_drawn)` in `outline_compiler.c`, with a comment at `outline_drawn` pointing there.

**Byte-fit hints.** `SKIPNOT(c)` and `SWAP(x)` are encoding selectors with identity native meaning: `SKIPNOT(c)` is `c` and `SWAP(x)` is `x` under g++. They choose between two encodings of the same computation, `spa i` over `sma` and `rcl 9s` twice over `rcr 9s` twice, where the binary records the authors' choice. G5 fails each if deleting it leaves the words unchanged, and G6 cannot see them, so their only evidence is the hash. They belong with `PLACE` and `ARGS_DONE`: hints that fit bytes, not semantics.

**Second corpus users.** `io_word` results (a direct JSP call, a computed call, a call through a pool pointer), `control_boxes()` and `extern HOMED` each had one corpus user or none. `thermostat` and `turnstile` use all three and mirror no lifted routine. Both run `iot 11` in SIMH: with the CPU's display option off, headless SIMH leaves IO unchanged on `iot 11` and does not stop, so a reader that clears IO first reads no buttons, as the native `control_boxes()` does. The M7 note that SIMH stops on `iot 11` was wrong; the frame check's control-box scenarios also run `read_control_boxes`.

**Naming.** A pass across `lift/` replaced short or opaque names with what the value means; each definition keeps the source's symbol in its comment. The main ones (source symbol in parentheses):
- `sqt` is `square_root` (`lift/square_root.c`, `tools/check-square-root-reference.py`); `sq1`, `sq2` are `root_passes_left`, `partial_root`.
- The outline's direction steps, pool words the outline compiler's code reads: `down_step_x`, `down_step_y` (ssn, scn), `out_step_x`, `out_step_y` (scm, ssm), `out_down_step_x`, `out_down_step_y` (ssc, csm), `in_down_step_x`, `in_down_step_y` (csn, ssd).
- `object_table.h`: `OUTLINE_STARTS` (not) is the table property holding each ship's compiled outline; `OUTLINE_CODE_SPACE` (nnn) is the free core the outline compiler writes into. `NOB` is `OBJECT_COUNT`, `SPINS` `ANGULAR_MOMENTA`, `OLD_CONTROLS` `PREVIOUS_CONTROLS`.
- The spaceship's gravity: `work` is `gravity_operand` (\t1), and the locals `d`, `f`, `q` are `capture_margin`, `distance_cubed`, `pull`.
- Locals in every file named for their meaning (`flame_dots`, `launch_coordinate`, `particle_count`, `routine_changed`, ...). Kept: `a` and `b` in multiply (interchangeable factors, which `integer_multiply` passes swapped), `a` in the sine series (the reduced angle, then the running sum), and the starfield's `x`, `y`.

**What the checks still do not prove.** The frame check runs 1412 of 1442 compiled code words, as after M7; the 30 it does not run are at the same places (M7 section). `check-divide-reference` calls dvd's entry; no check measures whether the other 29 run, and the hash covers them. The main loop has no native reference, since it runs generated code.

## Open questions and risks

- Runtime-generated code: M3 settles the writing side and M6 the entry: a jump through a HOMED pointer to a BLOCK function type, at its home, and a BLOCK at the return point (M6 section). M7's main loop stores the address (`mot, lac . / dap sp5`) through its extern declaration of `draw_outline`.
- `mex`'s runtime-built shift: settled by a HOMED shift run in place, with a typed native `xct` (Typed shifts section).
- Uninitialized `register` reads (mpy's `rcr(h, m, 18)` with garbage IO) are indeterminate in ISO C. The reference build maps IO to a global so it is defined there. Is that acceptable?
- `ENTRY_CELL` aliasing (sin/cos scratch, oc's pointer) is only correct while the owner's parameter is dead. Should the compiler prove that, or is a documented contract enough?
- pycparserext must parse GNU attributes on parameters and labels before declarations. A front-end spike should confirm this before anything else.
- `dislis` x4: settled in M4 by a cpp macro that defines one static inline function and its state per magnitude (M4 section). A static inline function with `int` parameters is still unimplemented.

## Next implementation step

None. M8 met the finish line of `docs/lift-playbook.md`: the image builds from `lift/` alone, the gate is green and every reference check is green.
