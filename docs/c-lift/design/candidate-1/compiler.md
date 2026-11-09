# swc: the compiler (candidate 1)

swc compiles the PDP-1 C dialect (`pdp1.h`) to Macro text. macro1 assembles that text, and the build compares the `.rim` sha256 with the oracle. swc never chooses an address. It picks instructions by rule, keeps C source order for layout, and lets macro1 do the rest: symbol values, the literal pool, and variable allocation.

## Pipeline and module map

```
C region file ──cpp -DPDP1_COMPILER -include pdp1.h──► pycparser AST + pragma list
   front.py   parse, collect `#pragma pdp1` lines into Directives (closed vocabulary)
   sema.py    resolve names; give every object a Storage; give every function an Abi;
              check the dialect's static rules (homed sites, consume, overlay, no spills)
   lower.py   statements and expressions -> Block IR (rules S, R, H, X, C)
   flow.py    if / loops / switch / returns -> laid-out word lists (rules L, O, W, C3)
   emit.py    Block IR -> Macro text (+ source map: word -> C file:line, rule id)
splice.py    regions.toml -> spliced .mac -> macro1 -> sha256 gate, per-region word diff
tests/       non-Spacewar dialect programs, run in SIMH and natively (g++ reference mode)
```

Tracing one C statement to its words takes three files: `lower.py` (which rule), `flow.py` (where it lands), `emit.py` (spelling).

## Core types (Python, sketched)

```python
class Storage:            # where an object lives; decided once in sema, never guessed later
    EntryWord(fn)         # jda parameter: the function's first word
    Homed(ptr, site)      # address field of the dereferencing instruction at `site`
    HomedWord(ptr, op)    # address field of a standalone data word with opcode op
    Inline(pos)           # punched at its definition (file-scope initialized)
    Placed(pragma_pos)    # function statics, or anything named in `place`
    MacroVar(name)        # \name; macro1 allocates it
    Overlay(of)           # shares another object's cell
    AC | IO | ACIO        # auto word | register word | dword locals

class Abi:  Jda(entry, inline: None | Exec(p) | Data(p)) | Jsp(io_param) | Jmp(returns_to) | Xct
class Operand: Sym(name, off) | Lit(value_expr) | Var(name) | Self | Rel(n)
class Word:  Insn(op, indirect, Operand, rule) | Skip(bits, invert) | Opr(bits) | Data(value_expr)
class Block: label, words: list[Word], falls_to
class RegState: ac: ValueId | None, io: ValueId | None   # the AC/IO value cache (R2)
```

`Word.rule` is mandatory. Every emitted word carries the id of the rule that produced it. This provenance is what `swc --explain` prints and what the honesty gate checks.

## Lowering rules

Rule ids match the trace comments in `examples/`.

### Instruction selection (S)

- **S1 constants.** A constant at the head of an expression loads into AC as follows: `cla` for 0; `law n` for 1..07777 or an address symbol; `law i n` for the ones' complement of 1..07777 (C `-041`); `lac (c` for anything else. A constant in any other operand position becomes the literal `(c`. A constant goes into IO with `lio (c`. Storing 0 is `dzm`. All numbers are emitted in octal (Macro's radix).
- **S2 increment.** As a statement, `++x` emits `idx x` and leaves the new value in AC. When `++x` is tested against 0, it emits `isp x`, which skips when the new value is >= 0.
- **S3 binary operators.** The left operand is evaluated into AC. The right operand must be a memory operand: a variable, a literal, `*p`, or a homed dereference. `+ - & | ^` map to `add sub and ior xor`. `>> n` and `<< n` map to `sar`/`sal`. Shift counts above 9 split into `9s` chunks followed by the remainder (`>> 11` is `sar 9s; sar 2s`). A right operand that needs computing is rejected with "name it". swc never invents a temporary.
- **S4 register places.** `r.io = m` emits `lio m`. `m = <IO value>` emits `dio m`. `*p = <IO value>` emits `dio i p`. `r.ac = m` emits `lac m`.
- **S5 builtins.** `mag` emits `spa; cma`. `swap` emits `rcl 9s` twice and `swapr` emits `rcr 9s` twice. `rcl/rcr/scl/scr/ral/rar/ril/rir/sil/sir` emit one shift instruction each (with S3 chunking). `mus`/`dis` emit one step. `-x` and `~x` both emit `cma`. Hardware builtins map 1:1 (`dpy` is AC=x, IO=y, then `dpy-i`; `flag(n)` is tested with `szf`; `sense(n)` with `szs`).
- **S6 operate merge.** Operate-group micro-ops (`cla cli clf stf cma ...`) produced by one C expression statement or one builtin call merge into one word when the hardware applies them in a fixed order. Micro-ops from separate statements never merge. `dpy(0, 0, 04000)` therefore emits `cla cli-opr`.

### Registers (R)

- **R1 locals are registers.** An `auto word` lives in AC, a `register word` in IO, and a `dword` in AC:IO, with each half tracked separately for liveness. Locals are declared at the top of the function, which keeps the code valid for the C++ reference build. sema runs liveness and rejects any program where a live local's register is clobbered by an instruction, a call (via clobber summaries), or a join with a disagreeing predecessor. There is no spill path.
- **R2 value cache.** AC and IO carry a `ValueId`: a constant, a variable's current value, or a deref value. A load whose value is already in the register is omitted. The cache is invalidated by stores to possibly-aliasing cells, by calls (per the callee's summary), and at labels (intersection over predecessors). A `volatile` read is never omitted. This one rule produces `dac sin` / `jda mpy` with no reload, `ocn = oc_to + 4` right after `idx oc`, and the cos tail call entering past `lac sin`.
- **R3 tests while AC is busy.** A sign test of a memory operand while AC holds a live value goes through IO: `lio m; spi`. IO must be dead at that point, or swc rejects the program.
- **R4 implicit moves.** Any AC-to-IO or IO-to-AC move the C implies is `swap`. A program that wants the `rcr` encoding writes `swapr` explicitly.

### Control flow (F, L, O, W)

- **F1 skip table.** `== 0` is `sza`, `!= 0` is `sza i`, `< 0` is `sma`, `>= 0` is `spa`, `<= 0` is `sma sza`, `> 0` is `sma sza i` (= `spq`). On IO, `>= 0` is `spi` and `< 0` is `spi i`. `flag(n)` false is `szf n` and true is `szf i n`. Equality against memory is `sas` (skip if equal) or `sad` (skip if different). `isp` has no inverse.
- **L1.** `if (c) J`, where J is one jump (`goto`, `continue`, `break`, or a valueless return to a slot) and c has an inverse, emits `skip(!c); jmp target`.
- **L2.** `if (c) S`, where S is exactly one non-skip word, emits `skip(!c); S`.
- **L3.** Every other if emits `skip(c); jmp Lend; S; [jmp Lend2; Lend: E]`.
- **O1.** `for (;;) B` and `while (1)` are B followed by a back-edge `jmp`. **O2.** `do B while (c)` is B, then `c` lowered as L1 with the loop head as target. No loop rotation and no entry jumps. **O3.** `#pragma pdp1 unroll` fully unrolls a loop with a constant trip count.
- **W1.** A `switch` with no default, whose cases cover 0..n-1 densely, becomes `add (.+3; dap .+1; jmp .` followed by one slot per case. A slot holds the case's code if that code is one word. It holds `jmp` to the target if the case is a single `goto` or a shared label. It holds `opr` if the case is empty and falls through. The last case's code starts in its own slot. An out-of-range value is undefined behavior, as in C.
- **Layout.** Emission order is C source order: functions, data, statements, and unreachable code after an unconditional jump (reached by `goto`). swc never reorders. Branch targets that have no C name are emitted as `.±n`. C labels that something else references are emitted as symbols. Adding a label does not change the `.rim`: line 318 was labeled in a copy and the sha256 was unchanged.

### Homed pointers (H)

- **H1.** A `homed` pointer p lives in the address field of the instruction that dereferences it in the statement labeled `p:`. That statement must contain exactly one direct dereference of p. With no initializer, the address field starts as `.` (the host's own address). One statement may carry several labels, homing several pointers (`mx1: mx2:`).
- **H2.** Everywhere else, `*p` is `op i host`. Host instructions never have the indirect bit set, so this is exactly one level of indirection.
- **H3.** p's rvalue is the whole host word (opcode bits included). Storing to p is `dap`, `++p` is `idx`, and comparing the post-`idx` value against a constant address c emits the literal `(OP c`, where OP is the host's opcode. sema checks that a homed rvalue only flows into address-field consumers (`dap`, a literal compare); `dac q` with p's value is rejected.
- **H4.** For a `homed_word(p, OP)`, the value `OP(p)` is the host word itself, so it lowers to `lac host`.

### Calls (C, X)

- **C1 jda.** Function f gets an entry word (initial 0) that is the first parameter's home. The prologue is `dap <link>`. The caller evaluates argument 1 into AC and emits `jda f`.
- **C2 inline operands.** For an *exec* operand, the caller emits one load word (`law`, `lac m`, or `lac (c`) after the `jda`; anything else is rejected. In the callee, the link is homed in the first instruction that reads the operand (`xct`, initial address 0), later reads are `xct link`, and the return is `jmp i link`. For a *data* operand, the caller emits the value word itself; the callee reads it with `lac i <slot>` and returns through the slot. In both cases `consume(p)` emits `idx link`. sema requires that `consume` runs exactly once on every path to a return, that AC is dead there, and that p is not read afterwards.
- **C3 return slot.** The textually last `return` (or the implicit one at the end) hosts `jmp .`. Every other return loads its value and jumps to that slot.
- **C4 shared exit.** A jda (or jsp) function whose every return is `return g(e)`, with g a jda function in the same unit, owns no slot. Its prologue patches g's slot. A return stores e into g's entry word and jumps to g's first instruction after its prologue. If R2 proves AC already holds g's parameter, the jump also skips g's leading reload of that parameter. This covers cos into sin, and idv into dvd.
- **C5 call through a word.** `AS_FN(T, e)()` evaluates e, then emits `dap .+1` and the ABI's call instruction with address `.`.
- **C6 jmp ABI.** Calling a `jmp` function emits `jmp f`. A call through a jmp-ABI code pointer that is homed at the call site emits the host `jmp .`. `returns_to(T, L)` exports label L, which must be the statement right after every such call.
- **C7 jsp.** The prologue is `dap slot`. A `register` parameter arrives in IO. A jsp function whose body is `return g();` with g also jsp emits only `jmp g`, because AC still holds the link.
- **X1 xct.** The function's body must lower to one word, and that word is the function. Arguments arrive in AC (or AC:IO for `dword`). A call is `xct f`. A call through a pointer to an xct function is `xct i p`, or `xct .` with the pointer homed.
- **Clobber summaries.** Each function gets a computed {AC, IO, flags} clobber set. `ocs` preserves IO, so `d.io` survives `ocs(d.io)`.

### Storage and pools (P)

- **P1.** A file-scope object with an initializer is punched at its definition. A file-scope object without any initializer is `\name`: macro1 assigns addresses in order of first appearance in pass 2 (`tools/macro1.c` `lookup`, `vars_addr++` on the first overbarred lookup). That order follows from emission order alone. swc never computes it.
- **P2.** A function `static` is placed after its function unless `place` moves it.
- **P3.** `overlay(x, f)` gives x f's entry word. sema checks that f is not active while x is live, using the call graph. An assignment between two names for the same cell emits nothing (self-copy elimination).
- **P4.** `place(x, ...)` emits the named objects' words at that statement or declaration position.
- **P5 literals.** Literals are emitted where they are used. macro1 dedups them by value in pass 2, in order of first appearance. But pass 1 reserves one pool slot per occurrence, duplicates included (`literal()`: `++lit_count` with no dedup). The pool runs 02767..03222 for 156 occurrences, 84 of them unique. The `variables` block starts right after the reservation, so **the total literal occurrence count moves every variable address**. A rule change that turns a `law` into a literal, or the reverse, shows up as a hash failure far from where it was made. The splice diff reports the `variables` address as its first check.
- **P6.** `org`, `reserve`, `constants`, and `variables` pass through as `N/`, `. N/`, `constants`, and `variables`.
- **Names.** A C identifier is the Macro symbol if it is at most 6 characters (macro1 `SYMLEN` 7). Otherwise, or if the symbol is not a valid C identifier (`1sc`), `#pragma pdp1 name` supplies it.

## Incremental splice-and-hash build

```toml
# regions.toml: disjoint, sorted source line ranges, each replaced by one C file
[[region]]  c = "src/sincos.c"   lines = [195, 254]
[[region]]  c = "src/mpy.c"      lines = [260, 301]
[[region]]  c = "src/sqt.c"      lines = [309, 343]
```

`swc build` runs these steps:

1. Read `source/spacewar3.1_complete.txt`.
2. Compile each region's C to a fragment. Fragments are cached under sha256(C + `pdp1.h` + `spacewar.h` + swc version).
3. Replace the region's lines with its fragment and write `build/lifted.mac`.
4. Run `macro1 -r -d`.
5. Compare the sha256 with the oracle.

The build is a pure function of its inputs, so re-running it is idempotent and a crash halfway leaves nothing to clean up.

When the hash differs, `splice.py` reports the following:

- whether the `variables` base moved (P5)
- the first differing address inside each region (lifted listing compared with `build/oracle.lst`)
- the C file:line and rule id that produced that word, from the source map

The listing comparison is a diagnostic only. The verdict is the hash.

Lift order: leaves first (sqt, mpy/imp, idv/dvd, sin/cos), then the tunable table, oc, the star displays (the `dislis` macro becomes a C preprocessor macro that defines four functions), mex/tcr/hp, ss1/ss2, and finally the main loop. Macro `define`s stay in the prelude until no unlifted region uses them. Symbols that a lifted region uses but does not define are declared in `spacewar.h`.

## Keeping the compiler honest

The failure to rule out is a compiler that emits remembered Spacewar words. These checks rule it out, each by construction or by a test that runs.

1. **No source access.** Tests run swc in a temp tree containing only the region C files, `pdp1.h`, and `spacewar.h`. `source/` and `build/oracle*` are absent. A lint fails on any path string that names them.
2. **Rule provenance plus a vocabulary lint.** Every word carries its rule id (above). A lint fails if any swc source file contains an identifier from the oracle's symbol table, or an address of 4 or more octal digits. Rules can only mention C constructs.
3. **Differential suite on non-Spacewar programs.** Each rule has at least two test programs, for example: ones' complement factorial; a table walk with homed cursors and `sas` bounds; a JIT that emits `add` chains and runs them through a jmp-ABI pointer; jda with exec and data operands; xct tables; dense switches; shared-exit tail calls. Each program runs twice: natively (`g++ -std=c++14 -include pdp1.h`, where `word` has ones' complement operators) and through swc, macro1, and SIMH pdp1. Final memory and registers must match. Rule coverage is measured from provenance tags.
4. **Lifted-routine equivalence.** Pure routines are run natively from the lifted C and in SIMH from the *oracle* binary at their oracle addresses, on at least 10k random inputs, and must match bit for bit. Native-only smoke run done so far: lifted `sqt` matches sqrt x 512 exactly at 7 points, and lifted `sin`/`cos` stay within 6.2e-5 of libm over [-6.2, 6.2]. The SIMH side is not built yet.
5. **Mutation sensitivity.** For each lifted region, swc makes mutated copies of the C: swap commutative operands, perturb a constant, reorder independent statements, flip a comparison. The emitted words must change at the predicted addresses. A compiler that ignored its input fails this.
6. **Pragma budget.** Pragmas may state ABI, storage, and layout facts only, never an instruction choice. swc reports pragmas per region, and a region whose pragma count grows is reviewed as possible memorization creeping in.
