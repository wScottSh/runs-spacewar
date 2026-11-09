# pdp1cc: compiler design (candidate 3)

pdp1cc compiles the pdp1c dialect (`pdp1.h`) to symbolic Macro text. macro1 stays the assembler and linker: pdp1cc never computes an address. It emits symbols, `\` pool references, and `(` literals, and macro1 resolves them. Two things follow from that split:

- The compiler's job is choosing the instruction sequence, which is the hard part. Layout arithmetic, which is easy to get wrong, stays in macro1.
- Partial lifts are cheap. A compiled region is Macro text, so it can replace the original lines in place.

Status: design only. The six hand traces in `examples/*.lower.mac` apply the rules below by hand. `examples/verify.sh` splices each trace into the original source and reassembles it with macro1. All six reproduce sha256 `8744e9c9…bdf`, singly and all together. This checks the rules as written. It does not check a compiler.

## Module map

```
tools/pdp1cc/
  cli.py        thin shell: build | lower | normalize | gate
  front.py      gcc -E -D__PDP1CC__ -include pdp1.h, then pycparserext GnuCParser -> C AST
  dialect.py    C AST -> typed IR. Resolves every name to a Storage, every function to a
                Conv, rejects anything outside the dialect with a message naming the rule
  ir.py         the domain types (below). No pycparser types escape front.py/dialect.py
  select.py     IR statements/expressions -> Word list. Owns AC/IO tracking and skips
  skips.py      condition -> skip encoding (pure table, unit-tested exhaustively)
  layout.py     orders Words: placement, exit cells, PLACE, fallthrough, ARGS_DONE,
                generated labels; checks one-symbol-per-cell
  emit.py       Word list -> Macro text (one line per word, rule id in the comment)
  rules.py      the rule registry: RuleId -> doc string, test list (see honesty gate)
  splice.py     lift.toml regions -> spliced source -> macro1 -> sha256; per-region cache
  normalize.py  C -> C for the reference build: operators on `word` -> w_* calls,
                register/dword locals -> the reference AC/IO globals
  gate/         corpus/*.c, simh runner, reference-build runner, coverage, grep gate
```

Call chain for one function: `dialect.lower_decl -> select.lower_fn -> layout.place`. That is three files. `emit` is a pure fold over the result.

## Core types (ir.py)

```python
# Where a C object lives. Chosen by declaration, never inferred from use.
Storage = (Acc()                       # automatic word / insn local; dword.hi
         | Io()                        # register local; dword.lo; JSP param
         | Pool(sym)                   # uninitialized static/extern POOL  -> "\sym"
         | Placed(sym, init, nopunch)  # initialized static/file-scope    -> "sym, init"
         | Homed(sym)                  # address field of the home instruction
         | Entry(fn_sym)               # JDA first param / ENTRY_CELL alias
         | CompileTime())              # C int: unrolls, instantiates, never stored

Conv = Jsp | Jda(inline: tuple[Byname | Inline, ...]) | Xct | Block

Operand = Sym(name, pool: bool) | Lit(Operand) | Here() | Num(int) | Plus(Operand, int)

@dataclass(frozen=True)
class Word:            # one 18-bit word of output, still symbolic
    op: Op | None      # None = data word
    i: bool
    operand: Operand | None
    labels: tuple[str, ...]
    rule: RuleId       # provenance: every word names the rule that produced it

Item = Word | Origin(addr) | Reserve(n)
```

Every word carries `rule`. That single field supports the trace output (`pdp1cc lower --trace`), rule coverage, and the gate in "Keeping the compiler honest".

## Lowering rules

Each rule has an id. The id appears in `--trace` output and in the `.lower.mac` comments.

### Storage (dialect.py)

| id | C | storage | notes |
|---|---|---|---|
| ST-AC | automatic `word`/`insn`/`code` local, `dword.hi` | AC | Live ranges must not overlap other AC values. A clobber while live is a compile error: "spill: name a static". No hidden temporaries. |
| ST-IO | `register` local, `dword.lo`, JSP param | IO | All `register` locals share IO. Overlapping live ranges are an error. |
| ST-POOL | `POOL`, or tentative file-scope definition without initializer | `\x` | Emitted with `\` on every reference (see pools). |
| ST-PLACED | initialized static or file-scope object | word(s) at definition point | Static locals go at function end, or at `PLACE(...)`. |
| ST-HOMED | `HOMED` pointer/code | address field of the `home(p)` instruction | Exactly one home per program. An uninitialized home's address field is `.`. |
| ST-ENTRY | JDA first param; `ENTRY_CELL(f)` object | f's entry word | Assigning a param to its own ENTRY_CELL alias emits nothing (oc: `ocp = dst`). |
| ST-CT | C `int` | none | Loops over `int` unroll; `static inline` with `int` params instantiate per call. This covers `repeat` and `dislis`. |

### Expressions (select.py). Operand order is instruction order.

| id | form | words |
|---|---|---|
| EX-LOAD | memory operand into AC / IO | `lac x` / `lio x`. A homed deref at its home is the home instruction. Any other `*p` is `lac i p`. |
| EX-CONST-AC | constant c into AC | 0 → `cla`. \|c\| ≤ 07777 → `law c` / `law i c`. Otherwise `lac (c`. |
| EX-CONST-IO | constant into IO | `lio (c` (IO has no immediate). |
| EX-BIN | `l op r`, op ∈ `+ - & \| ^` | Evaluate l into AC, then `add/sub/and/ior/xor r`. r must be a memory operand: variable, `*p`, or constant (→ literal). Anything else is a compile error that names the temp to introduce. |
| EX-UNARY | `-x`, `~x` | x into AC, `cma` |
| EX-SHIFT | `x >> n`, `x << n` (n is a CT int) | `sar ns` / `sal ns`, split into 9s chunks |
| EX-ROT | `ral/rar/ril/rir/sir(v,n)`, `rcl/rcr/scl/scr/mus/dis(h,l,…)` | One instruction per 9s chunk. Pair ops require h ∈ AC and l ∈ IO, otherwise an error. |
| EX-MOVE-IO | `register r = <AC value>` | `rcl 9s; rcl 9s`. This is the program's `swap`. A rotate in the other direction must be written `rcr(h,l,18)`. |
| EX-STORE | `x = e` | e into AC, then `dac x`. Store to a `register` target: `dio`. Store of 0 to memory: `dzm x`. Store to a homed pointer or `.addr`: `dap`. Store at a home: the home instruction (`dac .`). |
| EX-POSTINC-STORE | `*p++ = e` | `[e]; dac i p` (or `dio i p` from IO); `idx p`. AC then holds p. |
| EX-INC | `++x` as statement or value | `idx x`, `idx i p` for `++*p`. AC = new value. |
| EX-HOMED-CMP | homed pointer compared with a constant pointer | The constant is encoded with the home's opcode: `(lac mtb+30`. |
| EX-INSN | `insn` constructor constant | Literal of the encoded word, e.g. `(lac \sx1`, `(jmp sq6`, `(dpy-4000`. |
| EX-CODE | `CODE(f)` | f's address. ≤ 07777 → `law f`; `CODE(f)\|SIGN` → `lac (f 400000`. |

AC/IO tracking (TRACK). `select.py` keeps a small fact set: "AC holds value-of(e)" and "IO holds value-of(e)". A store keeps the fact. Any write to e's storage, or a call whose summary clobbers the register, kills it. A label with several predecessors keeps a fact only if every predecessor has it. A load whose value is already in the register is elided. Every hand trace depends on this: `dac sin / jda mpy / lac sin`, `*ml1 = K; *ml2 = K`, `ml1 = …; mx1 = ml1 + NOB`. Callee summaries say which registers a routine preserves. ocs preserves IO, which is why `jsp ocs` twice needs no `lio`. When the original reloads a value that is already in a register, the C writes `RELOAD(x)`, a counted hint (to add when needed; none of the examples needs it).

### Conditions (skips.py)

`skip_when(c)` returns the skip that skips exactly when c holds.

| c | skip_when(c) | | c | skip_when(c) |
|---|---|---|---|---|
| `x < 0` | `sma` | | `x >= 0` | `spa` |
| `x == 0` | `sza` | | `x != 0` | `sza i` |
| `x <= 0` | `sma+sza-skip` (640500) | | `x > 0` | `spq` (650500) |
| `io < 0` | `spi i` | | `io >= 0` | `spi` |
| `!flag(n)` | `szf n` | | `flag(n)` | `szf i n` |
| `!sense(n)` | `szs n0` | | `sense(n)` | `szs i n0` |
| `++m >= 0` | `isp m` | | `++m < 0` | none: use the IF-MULTI form |
| `acc == m` | `sas m` | | `acc != m` | `sad m` |

The compiler negates a condition by taking the complementary row. `SKIPNOT(c)` asks instead for `skip_when(c)` with the i bit flipped, e.g. `spa i` where the default would give `sma` (source line 731). A sign test of a memory operand while AC is live loads it into IO (`lio x; spi`). That is how sin tests `sin_cell` while holding the result.

### Control flow

| id | form | words |
|---|---|---|
| IF-SINGLE | `if (c) S` where S lowers to one word | `skip_when(!c); S` |
| IF-MULTI | otherwise | `skip_when(c); jmp Lelse; S…; Lelse:` (else-branch, if any, at Lelse) |
| LOOP-CLOSE | `do S while (c)` / `while (c);` with empty body | `top: S; skip_when(!c); jmp top`. With a comma condition, the earlier parts are statements at the `continue` target. |
| FOR-EVER | `for (;;) S` | `top: S; jmp top`; `continue` → `jmp top` |
| GOTO | `goto L`, C labels, labels on any statement (`if (a<0) si1: a += K;`) | `jmp L`; label on that statement's first word |
| SWITCH | `switch` over dense 0..n | `add (T; dap J; J: jmp .; T:` one entry per case. An entry is `jmp body`. An empty case that falls through is `opr`. The last case's body sits in its slot. |
| RET | `return e` | e into AC (or AC:IO), then `jmp R`. The source-last `return` owns the exit cell `R, jmp .` and needs no jump. |

### Calls and conventions

| conv | call site | callee | return |
|---|---|---|---|
| JSP | `jsp f`; a `register` arg must already be in IO | `f: dap R` | exit cell `R, jmp .` |
| JDA | first arg into AC; `jda f`; then one word per inline param: BYNAME → `lac <operand>`, INLINE → the constant | `f: 0` (entry = param) `dap R` | INLINE: `R, jmp .` exit, read param via `lac i R`. BYNAME: R is the `xct` at the first by-name read, later reads `xct R`, return `jmp i R`. Either way `idx R` skips the inline words (ARGS). |
| XCT | args into AC/IO; `xct f` | the body is exactly one word at f, or a compile error | AC / AC:IO |
| BLOCK | `jmp f`, arg in AC | no prologue | Owns its exit cell if it returns. A JSP/JDA function whose body is `return blk(…)` adopts blk's exit: its prologue is `dap <blk exit>` and its tail is a `jmp blk`. That jump is elided when blk is next in layout (FALLTHROUGH). |
| indirect | `call(v)` with v a variable | `jsp i v` | |
| indirect | `call(e)` with e an expression | `[e]; dap L; L: jsp .` | |

ARGS placement. The default puts `idx R` at the first instruction boundary after the last inline-param read that (a) dominates every return and (b) has AC semantically dead. Liveness runs through pair ops: in `rcr(h,l,18)`, l-out depends on h-in, so a dead result kills its input. The default reproduces imp and mpy. `ARGS_DONE();` overrides it, and oc uses it.

### Layout (layout.py)

- LAY-ORDER: items are emitted in the order they are defined in the region's C file. `AT(a)` emits `a/`. That is harmless when it creates no gap, because macro1 RIM blocks break only on gaps.
- LAY-EXIT, LAY-PLACE, LAY-FALLTHROUGH: as above.
- LAY-LABEL: a C name is its Macro symbol (6 significant characters, else `SYM("x")`). C labels are function-scoped and renamed on collision. Generated labels are `z<region-letter><n>`; the original has no `z` symbols. Two C entities may share a symbol only if they name the same cell: `BLOCK SYM("ml1") objloop` and `HOMED ml1`, whose home is objloop's first word. Otherwise it is an error.

## Literal and variable pools

These facts come from `tools/macro1.c` (`literal()`, `constants()`, `variables()`, `lookup()`):

1. Pass 1 counts every literal occurrence without dedup (`++lit_count`). The constants block reserves that many words (0234 here, 02767–03222), so the `variables` base (03223) depends on the occurrence count. Pass 2 dedups by value, and pool order is the order of first appearance. **Rule LIT-EVERY:** the compiler emits a literal at every constant operand it lowers and never CSEs literals. Occurrence count and first-appearance order then follow from the instruction sequence, which must match anyway. oc emits `(cma` twice for this reason.
2. A pool variable gets its address at its first overbarred occurrence in pass 2 text (`vars_addr++` in `lookup`). That includes occurrences inside literals such as `(lac \sx1`, which allocates `\sx1` first (03223). Pass 1 counts it only when the overbarred name is first inserted. **Rule POOL-EVERY:** emit `\` on every reference to a POOL object. Allocation order then equals first-use order in the spliced text.
3. A literal's value may be symbolic (`(lac mtb+30`, `(zo3`, `(jmp sq6`). macro1 evaluates it, and dedup compares values, so spelling does not matter.

## Incremental splice-and-hash build

```toml
# lift.toml -- one entry per lifted region, in any order
[[region]]  name = "sqt"      lines = "309-343"  c = "src/sqt.c"
[[region]]  name = "tunables" lines = ["77-96", "733-736", "1274-1282"]  c = "src/tunables.c"
```

`pdp1cc build lift.toml`:

1. Compile each region's C to Macro chunks, one chunk per line range, split at `REGION_BREAK()` markers in the C file. Cache key: sha256 of the C file, the headers it includes, and the pdp1cc version. A cache hit reuses the Macro text, so the build is idempotent and rebuilds are cheap.
2. Interface check before assembling. The region's defined symbols must be a superset of the symbols that unlifted text references from that line range. The reference set comes from the oracle's xref (`macro1 -d` symbol table and `build/oracle.lst`). The error names the missing symbol ("region ss1 must define srt").
3. Splice chunks into a copy of `source/spacewar3.1_complete.txt`, bottom-up so line numbers stay valid. This is the same procedure as `examples/verify.sh`.
4. Run macro1, compute sha256, compare. On a mismatch, diff the listing word by word and print the first differing address, the expected and actual word, and the rule id of the emitted word at that address. Error triage starts at a rule.
5. A step counts only if the full-program hash holds. A lift step is one new region; commit with the hash in the message.

Fully lifted end state: every line range is covered. The original file is then no longer needed. It is kept as the oracle.

## Keeping the compiler honest (anti-overfitting gate)

The failure to rule out is a compiler that emits memorized Spacewar words whatever the C says. `pdp1cc gate` runs every check below. The gate is a CI requirement. Text in this file does not enforce it.

- **G1 Reference build (meaning).** `normalize.py` rewrites operators on `word` to the exact `w_*` functions in pdp1.h. gcc compiles the result natively. For pure routines (sqt, mpy, imp, sin/cos, idv/dvd), the gate runs random inputs through both the native reference build and SIMH running the pdp1cc output, and the results must agree bit for bit. This shows the C means what the binary does without trusting pdp1cc.
- **G2 Non-Spacewar corpus.** `gate/corpus/*.c` are small programs written against pdp1.h (sorting, bignum add with `idx`/`isp` loops, a dispatch table, a BYNAME routine, a BLOCK with an adopted exit, runtime-built code). Each is compiled, run in SIMH (open-simh `pdp1`), and its result memory is compared with the reference build. `rules.py` requires every RuleId to be exercised by at least two corpus programs, and the coverage check fails otherwise.
- **G3 No memorized output.** A grep gate over `tools/pdp1cc/**`: no Spacewar symbol from the oracle symbol table appears as a string literal, and no 6-digit octal word from `oracle.rim` appears. Opcodes come from a single opcode table. The rule registry is the only place encodings are built.
- **G4 Provenance.** Every emitted word carries a RuleId (`Word.rule`). A word without one is a build error. The trace lists rule counts per region, so a "special case" shows up as a new rule with a single user.
- **G5 Hints earn their place.** Hints (`home`, `PLACE`, `SKIPNOT`, `ARGS_DONE`, `RELOAD`) have identity meaning. The gate removes each hint in turn and recompiles. If the output does not change, the hint is decorative and fails the lint. It also reports hints per 100 lines.
- **G6 Prediction tests.** The gate makes edits whose effect the rules predict and checks the predicted word-level diff. Swap `1 + ml1` to `ml1 + 1`: the only change is `law 1; add ml1` becoming `lac ml1; add (1`, plus the pool shift. Change `tno` to `-042`: exactly one word changes. A memorizing compiler fails these.
- **G7 Test before rule.** A new rule or rule change lands only with a corpus test that fails before the change. The region that motivated it must not be the only user.
