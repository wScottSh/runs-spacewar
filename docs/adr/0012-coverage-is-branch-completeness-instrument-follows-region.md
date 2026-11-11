# Coverage is branch-completeness of Ground Truth; the instrument follows the region

**Amended 2026-11-11.** The section "Instruments attach at the original's own seams" lets the original's structure drive the decomposition. It puts Processor boundaries at the 1962 `jda` and dispatch seams and refuses a finer split the source does not support. The EGS vision makes decomposition a convention, not a rule of compliance, and that convention pulls toward splitting each body into sub-Processors until atomic, composed on what they compute rather than on what any part was originally meant for (`../.github/CONTEXT.md` 117-129). This ADR's "Realization" is the rewrite under test, not the Realization region of `../.github/CONTEXT.md` 138-157. The vision governs.

Status: superseded by ADR-0017. Previously: accepted (organizing spine; supersedes ADR-0002; recasts ADR-0004 as its
consequence; reframes the Vector/Trace roles in CONTEXT.md and the sanity gate of ADR-0009)

This is the spine the rest of the Oracle hangs from. It is recorded late but governs early:
ADR-0001 (characterization suite), ADR-0004 (coverage strengths), ADR-0007 (game-scoped
domain), and ADR-0008/0009 (Vector records and their sanity gate) are all read as
consequences of it.

## The telos that forces it

The Oracle exists for one purpose: so a **Realization** — Spacewar rewritten in DIGS, or
eventually any language — can be asserted **byte-for-byte faithful** to the original. The
Oracle is the contract the rewrite passes. Every coverage question reduces to one: *is the
Oracle tight enough that anything passing it is byte-for-byte the original?*

Spacewar is a **deterministic transducer**. Pin its entire input surface — the `ran` seed,
the six sense switches, and the per-frame control words for both ships (CONTEXT.md → *Pinned
inputs*) — and the whole object-table sequence is a pure function of those inputs. "The
behavior of Spacewar" *is* that function. A Realization is faithful iff it computes the same
function. The Oracle's job is to pin the function tightly enough to tell.

A branching program's function is pinned only where **every reachable branch has been
observed**. A branch no test ever executed says nothing about a Realization's behavior there
— it may do anything and still pass. Against this telos that is not a weaker grade of done;
it is *not done*.

## The definition

**100% coverage = every reachable branch of Ground Truth, observed both ways, over the
game-scoped input domain (ADR-0007), measured mechanically from SIMH execution traces —
driven to exhaustive enumeration on the pure-math island where the domain is ≤2¹⁸.**

"Done" for the whole source = the union of the Oracle's scenarios lights every in-contract
branch. Uncovered branches self-identify from the trace-meter as named missing scenarios. A
branch reachable only by out-of-contract input is *correctly dead* (ADR-0007), not a gap.

This is one definition, **instrument-independent**, measured on the union of every scenario's
execution trace — never per-routine.

## What "branch" means — the coverage unit is decision coverage

"Branch" is not ambiguous on this machine, and the criterion is not novel. The PDP-1 has
**exactly one branching primitive: the conditional skip** — "Conditional skips were the only
means of branching; there were no conditional jumps" (masswerk pt1). Every decision in the
source is a single skip instruction (`sma`, `sza`, `spa`, `spq`, `szf`, `szs`, `sas`, `isp`,
and the micro-coded skip-group unions) with two outcomes: skip or fall through.

So the coverage unit is the textbook one — **decision (branch) coverage: every
conditional-skip instruction observed resolving both ways** — measured from SIMH traces. In
the settled subsumption lattice (Myers 1979; Ammann & Offutt 2008; DO-178C):

- Decision coverage **subsumes statement coverage**: over a connected control-flow graph,
  covering every skip both ways executes every instruction word. Statement coverage is not
  tracked separately; branch coverage gives it.
- Each PDP-1 decision is a **single condition** — one skip tests one boolean. Where every
  decision has exactly one condition, **MC/DC, condition coverage, and decision coverage
  coincide**. The compound-condition tier of the lattice collapses onto branch coverage, so
  branch coverage here is as strong as the DO-178C **Level A** criterion, not merely Level B —
  there is nothing stronger to reach for short of path coverage.
- **Path coverage** — every combination of decisions — is the unreachable ideal (loops make
  the path set infinite). It is exactly the residual the fault-model section below disclaims.
  We claim decision coverage, never path coverage.

Computed transfers (`dap .` then `jmp .`; the `dispatch` table at L440 with arms
`oc1..oc6`) are **multiway branches**, not a different kind of decision: a CFG node with N
out-edges, covered as edges — each realized target observed at least once over the game
domain. Self-modification changes a jump's *target*, never introduces a decision that is not
a skip, so it does not complicate the unit at all.

## The instrument follows the region (the inversion)

Coverage is the bar; *how* a branch is lit is an engineering choice made per region by
reachability. There are two instruments, and they are not rival definitions of done — they
are two ways to light branches:

- **Vectors — the pure-math island.** `sin`/`cos` (~L200), `mpy`/`imp` (~L260), `idv`/`dvd`
  (~L351), `sqt` (~L309) are `jda` subroutines: AC/IO in, AC out, no shared state. The
  cheapest instrument that lights their branches is direct enumeration at the entry point.
  On the unary routines (`sqt`, `sin`/`cos`, `random`) the domain is ≤2¹⁸, so the instrument
  reaches *past* branch-coverage to **exhaustive** — a proof of byte-exactness for any
  Realization, the strongest claim the Oracle can make. Vectors are observed, never
  hand-derived.

- **Traces — everything else (the primary instrument).** `ss1`, `tcr`, `mex`, `hp1`/`hp3`,
  inline gravity (~L1118), the collision test (~L870), and the main loop's self-modification
  (`dac i ml1` overwriting a slot's calc routine with `mex` at L889–891; slot iteration
  order; the `mtc` instruction-budget timing at L909/940) have branches reachable **only by
  playing the game**. The instrument that lights them is a scripted, pinned, fixed-seed match
  constructed to drive them; the per-frame object-table snapshot records the truth. No
  routine is isolated — the match walks the live branch and the snapshot *is* the
  characterization.

Because most of the file is entangled, **Traces are the primary instrument and Vectors are
reserved for the pure-math island**. This inverts the earlier Vector-first posture (the
superseded ADR-0002, and the "Plan A primary / Plan B backstop" framing CONTEXT.md once
carried), which made per-routine Vector capture the spine — over-building the easy pure
functions and unable to cheaply reach the entangled majority.

## Instruments attach at the original's own seams (salvaged from ADR-0002)

Where the 1962 authors drew a `jda`/dispatch seam, that is a natural place to attach an
instrument and a natural Processor boundary for the Realization. Where they inlined — gravity
inside `ss1`, the collision test inside the main loop — RUNS may inline too, rather than
imposing a finer, modern-ECS split the source does not support. Inline blocks are **not**
given synthetic isolated Vectors; they are covered transitively by the Traces that walk their
enclosing routine. The original's structure drives the Realization's decomposition; we do not
shape the game by a decomposition ungrounded in Ground Truth — that confident-but-unverified
move is exactly what produced attempt 1.

If a discrepancy ever cannot be localized because its enclosing Trace is too coarse to tell
where the divergence lives, the deliberate response is to add a synthetic mid-routine cut —
set the block's live preconditions, run entry-PC → exit-PC — for that block, and record it.
Until that evidence exists, the coarser Trace gate is correct.

## What "byte-for-byte" can and cannot mean (brutal honesty)

Two coverage obligations live here, and conflating them is the deep error under "isn't this
obvious":

1. **Oracle completeness — against Ground Truth.** Did the suite observe every reachable
   branch of the *original*? Mechanical, measurable, fully achievable. This is what "100%
   coverage" means.

2. **Realization adequacy — the suite vs a specific rewrite.** The Realization is a
   *different program with different branches* (e.g. the DIGS gravity Processor adds a
   `div == 0` guard the inline original has no entry for). Passing the suite guarantees
   byte-exactness only where the suite's coverage of the original also exercises every
   distinction the Realization introduces.

Obligation 2 has a mathematical floor, and the Oracle is honest about it rather than
pretending otherwise:

- Characterization / golden-master testing pins *observed behavior*; it does not infer
  correctness — which is exactly what we want (faithful = same-as-original, not "good game"),
  but it means the suite is only ever as strong as the observed domain.
- FSM conformance theory says the same rigorously: a finite test suite proves equivalence of
  two transducers only under a **fault model**. Chow's W-method is complete only given an
  upper bound on the implementation's state count, justified by white-box analysis of the
  design. No finite black-box suite proves equivalence of two arbitrary transducers.

So "byte-for-byte" resolves, per region, to the strengths ADR-0004 records — now *derived*
from this spine rather than asserted:

| Region | Domain | Strongest claim | Instrument |
|---|---|---|---|
| Pure-math unary (`sqt`, `sin`/`cos`, `random`) | ≤2¹⁸, enumerable | **Proof** — any passing Realization is bit-identical | Exhaustive Vectors |
| Pure-math binary (`mpy`, `idv`) | ~2³⁶ | Branch-complete + boundary sample; residual = an untested operand class | Sampled Vectors |
| Entangled / stateful (the rest) | unbounded | Branch-complete on the original, up to a fault model; residual = a Realization distinction no match reached | Traces |

The residual in rows 2–3 is the *floor* of testing a rewrite whose domain cannot be
enumerated, not a defect to engineer away. The response is the one already in the repo:
maximize to proof where the domain permits, fall to measured branch-completeness only where
enumeration is impossible, and treat any later divergence as a named addition to the sample
(a deliberate supersede). DIGS's own `deviation_manifest` is this same discipline at build
time.

## Consequences

- The backlog is *scenarios that light branches*, not *a Vector per routine*. The trace-meter
  names what is still dark.
- Rigor is proportionate **by construction**: the pure-math island gets exhaustive Vectors
  (cheap, and a proof); the entangled majority gets matches authored only until the meter is
  green. No routine is gold-plated the way sqt was.
- ADR-0004 is the region→strength mapping under this spine. ADR-0002 is superseded (its
  decomposition principle is preserved above). ADR-0008/0009 govern the *pure-math Vector*
  records and their sanity — a corner of the whole, not the spine.
- The one genuinely new piece of plumbing is the **coverage meter**: mapping SIMH execution
  traces back to source branches. The real new labor is *authoring matches to chase a
  specific dark branch* — forcing a collision geometry, a hyperspace breakout. It is bounded
  by the meter, not open-ended.

## Revisit trigger

If a Realization ever passes the full suite yet diverges from the Substrate, the divergence
names the missing branch or operand class; it is added to the suite and the relevant strength
tightened (a deliberate supersede). The bar — every in-contract branch of Ground Truth
observed — does not move; only the scenario set grows to meet it.
