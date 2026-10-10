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
- G1 runs as `tools/check-*-reference.py`, one per lifted routine group. Each compares the native build of the lifted C with SIMH running the routine in the oracle `.rim`, in one SIMH session, and compares every JDA entry word after every call. sqt covers 0..0177777.
- G2 (`pdp1cc gate`) compares the AC result, every placed and reserved word, and every JDA entry word after every call. Each rule needs two corpus programs that do not mirror a lifted routine (M2 section).
- G3 is `tools/check-g3.py`.
- G4 is structural: `Word.rule` is required and checked against the registry.
- G5 and G6 run in `pdp1cc gate` (M2 section). `tests/reject/` holds programs the dialect must refuse, each with the error it expects.
- G7 is a review rule: a new rule lands with its corpus programs. The row checker is not built.

**Not implemented yet.** while/do, `sas`/`sad`, indirect calls that return, a homed pointer read anywhere but its home, and the hints `SKIPNOT` and `RELOAD`. POOL, HOMED, INLINE parameters, the jump-table switch, `PLACE` and `ARGS_DONE` landed in M3.

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

## Open questions and risks

- Runtime-generated code: M3 settles the writing side (data written through a pointer, no execution spec). M6 must still choose the C form for entering the compiled outline (`sp5, jmp .` patched by `dap`) and for its return at `sq6`.
- `mex` builds `scl n` at run time (`ior (scl`) and executes it in place at `mi1`. That needs a "slot" (a writable one-word XCT routine) beyond the examples. Is `SLOT dword mi1(dword)` acceptable?
- Uninitialized `register` reads (mpy's `rcr(h, m, 18)` with garbage IO) are indeterminate in ISO C. The reference build maps IO to a global so it is defined there. Is that acceptable?
- `ENTRY_CELL` aliasing (sin/cos scratch, oc's pointer) is only correct while the owner's parameter is dead. Should the compiler prove that, or is a documented contract enough?
- pycparserext must parse GNU attributes on parameters and labels before declarations. A front-end spike should confirm this before anything else.
- `dislis` x4 (static inline + `int` params, per-instance homed cells, `jmp flo+R+1`) is untested against these rules.

## Next implementation step

Build `skips.py`, `select.py`, and `emit.py` for the sqt subset, then make `pdp1cc lower examples/sqt.c` output assemble to the oracle hash through `splice.py`, with the G2 corpus started in the same change.
