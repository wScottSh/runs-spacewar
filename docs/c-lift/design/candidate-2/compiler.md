# pdp1cc: compiler design (candidate 2)

The compiler turns dialect C (`pdp1.h`) into Macro text. macro1 (the oracle's
own assembler) turns that into the `.rim`. The compiler owns every decision
that shows up in the words: instruction choice, AC/IO use, code and data
layout, and the order in which literals and variables are first mentioned.
macro1 owns the arithmetic on symbolic expressions, literal-pool dedup, and
variable numbering. Nothing in the compiler names an oracle symbol, address, or
word.

Rule ids (L, C, S, A) are cited by the traces in `examples/*.trace.md`. The
words in those traces are machine-checked against `build/oracle.lst` by
`examples/check_trace.py` (467 rows, all agree). The checker proves each row's
text, word, and address match the oracle. It does not prove the rules produced
the rows; the hand trace beside each row argues that, and the compiler's
rule-tag report will check it once the compiler exists.

## 1. Module map

Call chain from C to words is four hops: `front` to `lower` to `layout` to
`emit`.

| module | does | exports |
|---|---|---|
| `front.py` | `gcc -E -include pdp1.h`, then pycparser. Lifts `_Pragma("pdp1 ...")` markers and typedef names (`cptr`, `inl_insn`, `inl_data`, `word`) onto the declarations they precede. Folds constants with ones' complement semantics. Checks the dialect (sema below). | `parse(path) -> Unit` |
| `lower.py` | Instruction selection, AC/IO allocation, AC value cache, condition lowering, calls, cursors, switch, unroll. One tree walk per function. | `lower_function(fn: Fn, env: Env) -> list[Item]` |
| `layout.py` | Orders items in declaration order, places link cells, fast-entry labels, in-stream data, `org`/`reserve`, `constants`/`variables` directives. Allocates nothing numeric. | `place(unit, lowered) -> Program` |
| `emit.py` | Prints Macro text, one instruction per line, each tagged `/ @file:line rule`. | `emit(program) -> str` |
| `splice.py` | Region table, splice into the original text, run macro1, hash gate, first-diff localizer. | `build(regions) -> Verdict` |
| `gate.py` | Anti-overfitting checks (section 6). | `check_all()` |
| `testing/` | Corpus runner, `pdp1ref` (host reference rewriter), SIMH-style stepper used only as a test tool. | |

Types (the whole IR; no other representation of code exists):

```python
@dataclass(frozen=True)
class Sym:      name: str                # macro1 symbol; "\\name" for a pool variable
@dataclass(frozen=True)
class Sx:       terms: tuple[tuple[int, "Sym|int|Dot"], ...]   # symbolic sum, macro1 does the arithmetic
@dataclass(frozen=True)
class Op:       kind: Literal["direct","indirect","literal","here"]; expr: Sx

@dataclass
class Ins:      mnem: str; opd: Op|None; indirect: bool
                rule: str; src: SrcLoc; labels: list[str]    # labels that point at this word
@dataclass
class Data:     expr: Sx; rule: str; src: SrcLoc; labels: list[str]
@dataclass
class Directive: kind: Literal["org","reserve","constants","variables"]; arg: int|None

Item = Ins | Data | Directive
@dataclass
class Fn:       name: str; conv: Literal["jda","jsp","cont","xct","fragment"]
                params: list[Param]; body: Stmt; labels: dict[str, Stmt]
@dataclass
class Param:    name: str; kind: Literal["word","inl_insn","inl_data"]
```

There is no `RawWord` or `Asm` node. A C `word` initializer or instruction
constant (`I_LAC(&x)`) becomes `Data` or an `Sx` literal, which is a typed value,
not an escape.

## 2. Storage placement (L)

**L1 Layout order.** Memory order is declaration order in the translation
unit. A function emits `[entry cell][prologue][body][link cell][labels placed
after]` in that order; nothing is reordered. `PDP1_ORG(n)` emits `n/`,
`PDP1_RESERVE(n)` emits `. n/` (octal, as in the source). Block-scope `static`
objects with initializers and `CELL_HERE` statements are placed in the stream at
their statement position. Reaching one by fall-through is a compile error
(`oc`: ocm/ocn follow `return`).

**L2 Storage classes.**
- Initialized global or `static` `word`/`word[]`: in the stream at the defining
  declaration. An earlier `extern` or tentative declaration is only a name
  (`sqt.c`: `extern word sq1` then `word sq1 = 0` after the routine).
- No definition with an initializer anywhere in the program: a variable-pool
  cell, referenced as `\name`. macro1 gives it an address at the `variables`
  directive in order of first reference.
- `cptr`: its home is its one `HERE`/`CELL_HERE` site. Zero or two sites is an
  error. `extern cptr` is a symbol whose site is in unlifted text or another
  unit.
- `extern word a[]`: a symbol only (the table `mtb`).
- Plain local `word`: AC-resident (A1), else spilled (A3).

**L3 Pools and order.** The compiler emits `(expr` for a literal operand and
`\name` for a pool variable and does nothing else. Facts about macro1 that the
compiler must respect (read from `tools/macro1.c`): pass 1 counts literal
*occurrences* (`lit_count`), and `constants` reserves that many words, so the
address of `variables` depends on how many literal operands were emitted, not on
how many are distinct. Pass 2 dedups by value, first appearance first. A pool
variable is numbered when pass 2 first evaluates `\name`, in emission order.
Consequences, all enforced:
1. Layout order equals emission order, so first-appearance order is source
   order.
2. No hoisting, CSE, or reordering of any operand whose text contains `(` or
   `\`.
3. The imm/literal decision (S2) is hash-visible: `law 1` instead of `lac (1`
   shifts `variables` by one word.
Observed in the oracle: `constants` at 02767, `variables` at 03223 (156 words reserved, 84 distinct
values), pool order 62210, 311040, ... in text order.

**L4 Cursors and cells.** `cptr p` is a pointer whose home is an instruction
cell `<op> Y`.
- `HERE(p)` places the cell at this program point. The opcode comes from the
  surrounding expression: load operand `lac`, right operand of `-` `sub`, of `+`
  `add`, assignment target `dac`, IO target `lio`, ...; initial Y is `.`. The
  cell executes as the access.
- `*p` anywhere else is indirect (`lac i p`).
- `p = q` is `dap p`. `p++` is `idx p`. Only these two write a cursor, so the
  opcode bits never change; this is the type invariant that makes S11 sound.
- Reading a cursor as a `word` value (`CELL_WORD(p)`) is the whole cell word.
  Reading it as an address into a non-cursor sink inserts `and (7777`; into a
  cursor sink it is free because `dap` drops the opcode.
- `CELL_HERE(p, "jmp")` places a plain storage cell `jmp .` (the `ocm`, `ocn`
  cells, copied as instruction words).

**L5 Regions.** A region is a line range of original text and a C file that
replaces it. Kinds: `unit` (whole declarations) or `fragment`
(`PDP1_FRAGMENT`: straight-line slice of a routine, no entry, no link, no
return). Labels the remaining original text refers to must be defined by the C;
`PDP1_AS(name)` fixes a Macro name that would clash with libc (`sin`, `cos`).

## 3. Calling conventions (C)

**C1 `PDP1_JDA` (arg in AC).** Entry cell `E` holds the argument (parameter 0's
home). Prologue: `dap L` where `L` is the link cell. Call site: evaluate arg0
into AC, `jda E`. `ENTRY(f)` names the entry cell from outside; inside `f`,
parameter 0 is that cell, so writing it (`sqt`: `x = 0`) is the remainder
reuse of idiom 2, spelled in C.

**C2 `PDP1_JSP`.** No entry cell, no arg in AC (AC is the return address).
Prologue `dap L`. Call: `jsp F`. Arguments travel in globals or IO (`ocs`
reads `IO`). Calls clobber AC and IO.

**C3 Link cell.** Two kinds.
- `jmp` kind (no `inl_insn` parameter): placed immediately after the textually
  last `return` statement, so the last return falls into it and earlier returns
  `jmp` to it; if there is no `return` and the end is reachable, at the end of
  the body. Other code (labels, gotos) may follow in the function (`sin`: `si2`).
- `xct` kind (has an `inl_insn` parameter): placed at the first read of that
  parameter in text order.

**C4 Inline arguments.** After `jda f`, the call site emits one word per
inline parameter: for `inl_insn` the one-word fetch `lac X` of that argument
(sema: the argument must lower to one non-transfer word: variable, indirect,
literal, or HERE cell), for `inl_data` the raw word. In the callee:
- `inl_insn` read: first read is the link cell itself, later reads `xct L`.
- `inl_data` read: `lac i L`.
- `skip_inline(n)`: `idx L` n times. It is explicit because the original puts
  it at different points (`imp`: after the call; `mpy`: at the exit).

**C5 Return.** `return e;` evaluates `e` into AC then reaches the link cell
(fall-through if this is the last return, else `jmp L`; `jmp i L` for xct
kind).

**C6 Tail call with link forwarding.** If a `PDP1_JDA` function's body is
`return g(e);` and `g` is `PDP1_JDA` with a jmp-kind link and a recorded fast
entry, then: prologue `dap g.L`, evaluate `e`, `dac g.E`, `jmp g.fast`. The fast
entry of `g` is the word after the first load of its parameter into an
AC-resident local. This is `cos` (`examples/sincos.trace.md`). If a condition
fails, the normal call-return sequence is emitted. The compiler compiles `g`
before `f` (dependency order), and the compiled text defines `g_f` for the fast
entry.

**C7 Indirect call.** `CALL_FN(w)` where `w` is a code address: put `w` in AC
unless the cache says it is there, then `dap L` / `L: jsp .` with `L` the next
word. This is the general function-pointer lowering for `PDP1_JSP` callees.

**C8 `PDP1_CONT`.** Entered by `jmp`, no link of its own; a call in tail
position is `jmp f`; any other use is an error. These are loop heads and
resume points that C cannot express as labels across functions (`ml0`, `sq6`).

**C9 `PDP1_XCT`.** Body must be `return <one-op expression of the parameter>;`
lowering to one non-transfer word. No entry, no link. A call evaluates the
argument into AC and emits `xct f`. The table entries `tno`, `tvl`, `rlt`, ...
are these (`examples/tunables.trace.md`).

## 4. Instruction selection and allocation (S, A)

Accumulator model. Every expression is evaluated into AC. A binary operation
needs its left operand in AC and its right operand *simple*.

**S1 Operands.** Simple operands: direct (`add x`), indirect through a pointer
variable or cursor (`add i p`), literal (`add (k`), a HERE cell. A non-simple
right operand is evaluated first into a temp (A3). If the operation is
commutative and only the left is non-simple, swap.

**S2 Immediates into an empty AC.** `0` is `cla`. A constant whose value (after
ones' complement) is in [-07777, 07777] is `law k` or `law i |k|`. An address
constant (symbol, function, array) is `law sym` (12-bit). Anything else, and
every symbolic constant with opcode bits (`I_*`, `mex+400000`), is `lac (expr`.
As a right operand a constant is always `add (k`. A zero store is `dzm`.

**S3 Binary operators.** `+ - & | ^` are `add sub and ior xor`. Unary `-x` and
`~x` are both `cma` (ones' complement negation is complement). With AC empty and
a commutative `+ & | ^`, if exactly one operand is a law-able immediate it goes
first (`law 1 ; add ml1`, which uses no pool word). Otherwise source order
decides (`lac (62210 ; add cos` for `HALF_PI + x`). The author controls the
order by writing it.

**S4 AC value cache.** The compiler tracks what AC holds: `Var(x)`, `Const(k)`,
or `Unknown`. After `dac x`, `dap x`, `lac x`, or `idx x` AC holds `x`; after an
operation it holds the expression. A load of a value AC already holds is
elided. Cleared at labels (except the live-in AC-resident local, A1), calls,
`xct` of an unknown word, and any write to a cell the cached expression reads.
`volatile` objects are never elided.

**S5 Stores.** `dac`; constant zero `dzm`; IO `dio`; assignment to a cursor
`dap`; assignment through `*p` `dac i p`. Chained `a = b = e` stores right to
left. The value of an assignment expression is in AC after the store.
`IO = e` loads IO only from a memory operand (`lio x`) or literal (`lio (k`).

**S6 Conditions.** `skip_when(P)` is one skip word; `branch(P, T)` is
`skip_when(not P) ; jmp T`.

| P on AC | skip_when(P) | skip_when(not P) |
|---|---|---|
| `< 0` | `sma` | `spa` |
| `>= 0` | `spa` | `sma` |
| `== 0` | `sza` | `sza i` |
| `!= 0` | `sza i` | `sza` |
| `<= 0` | `szm` (`sma+sza-skip`) | `spq` (`szm i`) |
| `> 0` | `spq` | `szm` |

IO `< 0`: `spi i` / `spi`. `flag(n)`: `szf n i` / `szf n`. `sense_switch(n)`:
`szs n i` / `szs n`. `a == b`: `lac a ; sas b` skips when equal; `a != b`: `sad b`.
`if (c) S` where `S` is one non-transfer word: `skip_when(not c) ; S`, no jump
(`spa ; cma`). Otherwise `skip_when(c) ; jmp Lend`. `++v >= 0` and `++v < 0` as a
condition fuse to `isp v` (index and skip when the new value is non-negative).

**S7 Pointers.** `*p` indirect; `p++` as a statement `idx p`; `*p++ = v` is
`dac i p ; idx p`; a `word *` pool variable stores with `dac`, a `cptr` with
`dap`.

**S8 Shifts.** Builtins map to one instruction. Count n > 9 splits into 9s then
the remainder (`rcr(x,18)` is `rcr 9s ; rcr 9s`; `scr(x,17)` is `scr 9s ; scr 8s`).
`rcl` and `rcr` are distinct and never normalized into each other.

**S9 Switch.** Dense `case 0..n-1`: `add (. 3 ; dap . 1 ; jmp .` then the
table. If every case but the last has a one-word body, the slots are the bodies
(so `case 0: nop();` falls into slot 1, as in C), and the last case's body
follows the table. Otherwise each slot is `jmp Lk`. Out-of-range is undefined,
as in C.

**S10 Unroll.** `PDP1_UNROLL` before a `for` with a constant trip count emits the
body n times; the loop variable has no cell. Without the pragma a `for` is a
counted loop.

**S11 Cursor compare.** `++p != (cptr)ADDR` is `idx p ; sas (op ADDR ; jmp T`
where `op` is p's HERE-inferred opcode.

**A1 AC-resident locals.** A function-scope `word` local that is not
address-taken and not `volatile` lives in AC while its live range holds: no
instruction that defines AC occurs between a def and a use on any path, and every
predecessor of a label that uses it agrees (`t` flowing into `oce`/`ocd` in
`oc`). Defining instructions: loads, arithmetic, `idx`/`isp`, `jda`/`jsp`
results, shifts. Not defining: `dac dap dio dzm lio sas sad`, skips, `jmp`.
**A2 IO.** IO is a global register only the author touches (`IO = ..`, `IO`
reads, combined shifts, `mus`). The compiler never allocates temps to IO and
never preserves it across calls.
**A3 Spill.** If A1 fails, the value goes to a compiler temp `\_tN` (a pool
variable) and `PDP1_NOSPILL` turns that into an error. Every function in the
Spacewar lift is under `PDP1_NOSPILL`; a spill there means the C is not the
original's shape and must be rewritten.

## 5. Incremental splice-and-hash build

```
regions.toml
  [[region]] name="sqt"  lines=[304, 343]  c="lift/sqt.c"   kind="unit"
  [[region]] name="torp" lines=[1273, 1285] c="lift/tcr_launch.c" kind="fragment"
```

`splice.build(regions)`:
1. Compile each region's C to `out/<name>.mac` (cached on the hash of the C,
   `pdp1.h`, and the compiler source).
2. Copy `source/spacewar3.1_complete.txt`, replacing each region's lines with
   its `.mac`. Check each range starts and ends on a statement boundary (no
   unmatched `define`/`term`). Keep a `splice.map` from output line to
   (region, C line, rule id).
3. Run `build/macro1 -r -d` on the result.
4. Verdict is `sha256(rim) == 8744e9c9...`. Nothing else is a pass.
5. On mismatch, diff the produced `.lst` against `oracle.lst` word by word, take
   the first differing address, map it through `splice.map`, and report
   (address, expected, got, region, C line, rule id). A symbol that lifted text
   defines and unlifted text uses (or the reverse) and does not resolve is
   reported before assembling.

Properties: the build is a pure function of (original text, region C files,
compiler); re-running it is a no-op. Regions are independent, so any order is a
legal lift order; the intended order is leaves first (`sqt`, `mpy`, `imp`,
`sin`/`cos`, then callers). `lift-state.json` lists the committed regions; CI
replays prefixes 0..N and requires the hash to hold at each one. A region that
shifts a pool or variable count breaks the next region's words, so the hash at
the prefix localizes the culprit.

When every region is lifted, `emit` also writes the prelude and `constants` /
`variables` lines from `PDP1_POOL()` and `PDP1_VARS()`, and the original text
is no longer read.

## 6. Keeping the compiler honest

The failure to prevent: output that matches because the compiler contains the
answer. Controls, each checked in CI:

1. **Assembly-blind compile.** `compile` runs with `build/` and `source/`
   unreadable (a landlock/strace test asserts it opens neither). The only
   oracle contact is `splice` reading the final hash and the `.lst` for
   localization after compilation.
2. **Deny-list lint.** `gate.py` builds a deny set from `oracle.lst`: every
   user symbol, every 5-digit address, every 6-digit word. It scans
   `compiler/` and the rule tables and fails on any hit. Rules are stated over C
   constructs, never over names or numbers.
3. **No escape hatch.** The IR has no raw-word or text node; a lint rejects
   builtins named like `asm`, `raw`, `emit`; the front end rejects `__asm__`.
4. **Rule provenance.** Every emitted line carries a rule id. The build writes a
   rule-hit table: Spacewar sites per rule, corpus tests per rule. A rule with
   fewer than two Spacewar sites, or no non-Spacewar witness, is marked
   `ONE-OFF` and blocks merge until a written justification states the property
   of C it implements. `S9`, `C6`, `C7` start as `ONE-OFF` candidates and need
   corpus witnesses.
5. **Semantic corpus.** `testing/corpus/` holds non-Spacewar dialect programs
   (sieve, insertion sort, decimal print, gcd by `idv`, fixed-point multiply
   table, a cursor-walked linked list, a dispatch-table VM, a self-modifying
   counter via `HERE`, an `inl_insn` helper, a tail-forwarded pair). Each is
   compiled with the same rules, run in the stepper, and compared with the
   `pdp1ref` host build (operators rewritten to the `w_*` functions in
   `pdp1.h`). The stepper is a test tool; it never ships and is not linked
   into any output.
6. **Mutation check.** For each rule the harness flips it to its alternative
   (commute off, cache off, fold off, split order, ...) and requires the corpus
   *or* the hash to fail. A rule no test notices is dead and gets deleted. A
   rule only the hash notices is an overfit suspect and needs a corpus witness
   showing the alternative is semantically wrong or at least distinguishable.
7. **Metamorphic checks on the Spacewar C.** Rename labels: words unchanged.
   Swap `a + b` for non-small operands: only those words change, in the
   predicted way. Change a constant: only its pool word changes. Add an unused
   literal: `variables` moves. These show the output is a function of the C.
8. **Reference lockstep (stage 2).** The `pdp1ref` build of the full Spacewar C
   and `oracle.rim` run in the stepper on scripted control input and are
   compared on the display-point stream for N frames. This is the check that the
   C *means* what the binary does, independent of byte equality. It needs a host
   model for `CALL_FN` and `ENTRY`; see open problem 6.

Not covered by any gate: whether a lifted function is readable C rather than
assembly in C clothing. That is a review judgment; the nearest mechanical proxy
is that `PDP1_NOSPILL` plus the lack of any raw node forces the C to carry real
expression structure.

## 7. Open problems

1. **Authored choices that the C must spell.** `load` via `lio`/`dio` (written
   `IO = k; x = IO`), `rcr` vs `rcl` swap, operand order, `sma+sza-skip`. Each is
   one spelling in C, but a long list of such spellings is the sign of a rule set
   drifting toward the source. Gate 4 and 6 watch this.
2. **Resume points across routines.** `sq6` is the instruction after the ship
   code's `sp5: jmp .`; the generated code jumps back to it. `PDP1_CONT` gives a
   C form (`extern _Noreturn void sq6(void)` and `I_JMP(FN_ADDR(sq6))`), but the
   ship routine must be split into a `HERE`-jump half and a `PDP1_CONT` half whose
   boundary sits in the middle of today's `ss1`. Not yet lifted; `jmp flo+R+1`
   is the same shape.
3. **Runtime-built instruction, executed** (`mex`: `ior (scl ; dac mi1` then
   fall into `mi1: hlt`, and `msh: xct .` over the two-word `mst`). The syntax
   exists (`EXEC_HERE` cell, a cursor with op `xct`), but a C reference meaning
   exists only for the shift group. Weakest idiom.
4. **AC joins.** `si3`, `oce`, `ocd` require AC-resident values to agree across
   incoming edges. Checked, but fragile to edit.
5. **Assembler-time structure.** `mtb`'s column layout (`nx1=mtb nob` ...), the
   `mark` star catalog (decimal data with `repeat 8, Y=Y+Y`), and the 4x `dislis`
   macro need a C struct view plus constant expressions (and the preprocessor for
   `dislis`). Straightforward but unproven here. `examples/tunables.trace.md`
   takes `ntr` on trust.
6. **Host model for the lockstep gate.** `ENTRY(f)` is a global per function,
   `inl_*` parameters are ordinary parameters, `CALL_FN` needs a word-to-function
   table. Not designed in detail.
