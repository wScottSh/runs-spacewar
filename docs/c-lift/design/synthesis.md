# Design synthesis

The arena ran three runners: candidate 1 and candidate 3 on Opus, candidate 2 on Sonnet. A Sonnet cross-judge scored them, and the orchestrator read all three. The candidates stay under `candidate-*/` as the record.

## Base: candidate 3

Candidate 3 (`candidate-3/rationale.md`, `compiler.md`, `pdp1.h`) is the contract. The cross-judge and the orchestrator agree on it.

- **Smallest surface.** The C storage class decides placement, and the compiler never invents temporaries. Automatic means AC, `register` means IO, an uninitialized static goes to the `\x` pool, an initialized static is placed where it is defined, `HOMED` means the address field of an instruction, and a JDA parameter lives in the entry word.
- **Strongest honesty gate.** G5 deletes each hint and checks that the output changes. G6 makes prediction edits. G7 requires a test before any new rule.
- **Only machine-checked evidence.** It is the only candidate whose hand lowerings were spliced and assembled to the oracle hash (`candidate-3/examples/verify.sh`).
- **Agreement.** Candidates 1 and 3 converged independently on the same core model: storage class as register allocation, an AC/IO value cache, source-order layout, macro1 kept as the assembler, a rule id on every emitted word, and a non-Spacewar corpus run in SIMH. That convergence is the main agreement signal.

## Grafts

- **From candidate 1: the executable reference.** Under g++ with `-include pdp1.h`, `word` becomes a C++ class with ones' complement operators, so the lifted C runs natively. This replaces candidate 3's `normalize.py` rewrite, which was never built. Candidate 1 already used it to catch the octal `repeat` bug.
- **From candidate 1: mutation sensitivity and no-source-access.** The C is mutated and the emitted words must change at the predicted addresses. The compiler runs in a tree without `source/` or `build/oracle*`. These go into G3 and G6.
- **From candidate 1: three forms.** Duff's device is the form for `bpt`'s computed jump into the unrolled `starp` block. A cpp or `static inline` instantiation is the form for `dislis` ×4. Each function gets a clobber summary.
- **From candidate 1: P5 diagnostic.** On a hash mismatch, the first thing reported is whether the `variables` base moved. Pass 1 reserves one pool slot per literal occurrence, 156 occurrences for 84 unique values, so a single `law` turning into a literal shifts every variable.
- **From candidate 2: row checker.** `check_trace.py`, which assembles each row separately and compares it with the listing, becomes a diagnostic beside the hash.
- **From candidate 2: rule-hit table.** It flags any rule used by only one site as ONE-OFF, so an overfit rule shows up.

## Rejected

- **`pdp1_exec`, `pdp1_call`, `pdp1_jump` reference specs** (candidate 3). They read as an interpreter in the header, which the operator ruled out. Generated code is plain data: instruction words built by `insn` constructors and stored through a pointer, then entered by a jump. The reference build does not execute generated code. Its correctness rests on the hash, plus SIMH running the compiled corpus.
- **Global `IO = x` and `HERE()` on every cursor** (candidate 2). This reads as assembly in C.
- **Pragmas for everything** (candidate 1). Candidate 3's macro spelling (`JDA`, `BYNAME`, `HOMED`) reads better. If pycparser cannot parse GNU attributes, the macros expand to `_Pragma("pdp1 ...")` instead, which gcc -E turns into `#pragma` lines that pycparser parses. The first implementation spike settles this.
- **Explicit `consume(p)` everywhere** (candidate 1). Candidate 3 derives `idx R` placement from liveness and needs `ARGS_DONE` only in oc. Keep the derived rule and fall back to the hint only where the derivation provably fails.

## Errors found during judging

- **Candidate 3 `mpy.c`.** The loop is `i < 21`, which C reads as decimal 21. Macro `repeat 21` is octal: the oracle has 021 = 17 `mus` words at 00205-00225. The hand lowering emitted 17, so the hash passed while the C said 21. This is the clearest evidence that hand traces do not tie the C to the words, and that only a real compiler does. Fix: `i < 021`.
- **Candidate 2 `impmpy.c`.** It uses `017`, which is 15. That is also wrong. The cross-judge marked it correct, and that was a mistake.
- **Uninitialized `register` read.** `rcr(h, m, 18)` with `m` uninitialized, used to move AC into IO, is indeterminate in ISO C. It needs a form that does not read `m`. The implementation decides which.
- **Labels inside `if` bodies targeted by `goto` from outside** (`si1:` in sin). This is legal C. Keep it, but note it in the dialect docs as the form for irreducible flow.

## Verification plan (phase F)

The design is verified only by a compiler that produces the hash from the C. Hand traces do not count. Order:

1. Front-end spike: confirm the parsing route for the dialect macros (pycparser or pycparserext, or the `_Pragma` fallback).
2. `pdp1cc` for the sqt subset, `splice.py`, and `lift.toml`. `build` must produce sha256 `8744e9c9…` with region 309-343 compiled from `lift/sqt.c`.
3. Reference build: `g++ -include pdp1.h lift/sqt.c` checked against SIMH running the oracle binary at `sqt` over the full 0..0177777 input domain.
4. Start the G2 corpus in the same change, with at least two programs per rule used.
