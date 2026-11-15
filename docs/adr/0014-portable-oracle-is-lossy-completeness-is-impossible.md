# The Portable Oracle is a lossy projection with a fault-model residual — completeness is impossible, not deferred

**Amended 2026-11-15.** The impossibility holds for Checks and Vectors. The user names the identical binary as the oracle that proves the conversion ("The only way for an oracle to prove that it is exactly the same is that when you compile it, it becomes the exact same binary again"; `../.github/CONTEXT.md`, Conversion). This ADR doesn't apply to the image.

Status: amended by ADR-0017 (only the impossibility holds; the Portable Oracle's projection rules went with ADR-0015). Previously: accepted (closes, permanently, the recurring "can we make a perfect/complete Oracle?" question; the consequence of ADR-0012's fault-model clause applied to the Realization-facing decode)

This ADR exists to **end a conversation that has recurred at least three times.** The answer to "can the Oracle — or the Portable Oracle — be made perfect/complete?" is not "not yet" and not "it's hard." It is **impossible**, on three independent theoretical results *plus this project's own prior doctrine*. If you are reading this because you are tempted to build a *completeness witness* for the Portable Oracle, or to "just implement the complete oracle" — **stop, and read this first. It already answers you.**

## The decision

A **perfect / complete** Oracle — one whose *passing proves* a Realization is behaviorally identical to Ground Truth — **cannot exist** for the entangled/stateful majority of Spacewar. Therefore neither can a perfectly-complete **Portable Oracle** (the lossy, address-free projection defined in `CONTEXT.md`).

The achievable ceiling is **best-effort inside a fault model**: exhaustive Vectors on the bounded math island (a genuine proof there, ADR-0004), branch-complete Traces everywhere else, and — for the Portable Oracle — a **lossy projection with a named residual**. "Implement the complete oracle" is **not a selectable option**; it misrepresents an impossibility as a backlog item.

This is a **floor established by mathematics, not a gap left by effort.** More engineering tightens the sample and lights more branches; it *never* removes the residual.

## Why — three independent walls, then our own doctrine

**1. No finite suite pins an unbounded function (FSM conformance).** For *any* finite test suite `T` with longest trace length `N`, one can constructively build a faulty implementation that agrees with Ground Truth for the first `N` inputs and then diverges: it passes `T` identically yet is a different function. Completeness requires restricting the space of candidate implementations — a **fault domain** / bounded state count. Chow's W-method is complete *only* under a state bound, and Chow justified that bound by **white-box** analysis of the design, never by black-box observation.
- *Completeness of FSM Test Suites Reconsidered*, arXiv:2410.19405 — https://arxiv.org/html/2410.19405v1 — "For any (finite) test suite T for 𝒮, we can trivially construct a faulty implementation that passes T"; a fault domain is a **necessary precondition**, not an optional tightening.
- *FSM-based conformance testing methods: A survey*, ScienceDirect — https://www.sciencedirect.com/science/article/abs/pii/S0950584910001278 — W-method completeness requires a bounded-state assumption, justified white-box.

**2. No finite experiment identifies hidden state (Moore 1956).** Observed transitions are always consistent with a *larger* machine carrying state the experiment never distinguished. A dropped machine-timing word (e.g. the `mtc` instruction-count budget, source line 665/677) is a concrete instance of exactly this hidden state.
- E. F. Moore, *Gedanken-Experiments on Sequential Machines* (1956) — https://www.semanticscholar.org/paper/Gedanken-Experiments-on-Sequential-Machines-Moore/a6021735e8de4f32010c6313396432d99bbe2440 — "there exist other machines experimentally distinguishable from S for which the original experiment would have had the same outcome."

**3. Equivalence and "is X ever read" are undecidable in general (Rice).** Behavioral equivalence of two programs, *and* "does Ground Truth ever read address X to compute the next frame," are both non-trivial semantic properties → no algorithm decides them in general. The load-bearing corollary: **dynamic reachability ≠ static reachability.** "Never read forward across the traces we ran" **cannot** be upgraded to "never read forward on any reachable execution."
- *Rice's theorem*, Wikipedia — https://en.wikipedia.org/wiki/Rice%27s_theorem.

**4. We already wrote this down — this ADR just makes it un-reopenable.** ADR-0012: *"No finite black-box suite proves equivalence of two arbitrary transducers"*; the residual is *"the floor … not a defect to engineer away."* ADR-0004 hard-codes enumeration-as-proof *only* where input-domain cardinality (fixed by instruction width) permits, and branch-complete elsewhere. This ADR is that doctrine, restated for the Portable Oracle so the question stops recurring.

## Consequences — the Portable Oracle's projection rules

The Portable Oracle drops PDP-1 implementation artifacts (machine-timing words, self-modified code addresses). Which drops are legitimate is governed by these rules, which follow directly from the walls above:

- **Read-set analysis is inclusion-only.** A word *observed read-forward* on the Traces **provably belongs** in the portable fingerprint — use this to catch a load-bearing field someone was about to drop. It **may never certify a drop** — that is the undecidable direction (wall 3). It is a *risk-reducer, not a completeness proof*. **Never call it a "witness."**
- **Drops are white-box engineering arguments, not witnesses.** The only legitimate justification for dropping a word is a reading of the PDP-1 **source** arguing the word never feeds the dynamics — Chow's own "justify by design analysis" move. Label it an *engineering argument*; it is not a black-box proof and must not masquerade as one.
- **A wrong drop is a deliberate supersede.** A dropped word later shown to matter is a `deviation_manifest` / supersede entry (the ADR-0012 mechanism) — the residual has a home; it is never laundered into "proven complete."
- **"Same" is exact, never epsilon.** Within the kept fields, equality is exact — bit-exact on raw numeric words, enum identity on decoded state fields. The residual lives entirely in *what is kept vs dropped*, never in a tolerance.

## Do not reopen

If a future session proposes a "completeness witness," a "perfect fingerprint," or "let's just implement the complete oracle" — **it is already answered here: impossible, by Rice + Moore (1956) + FSM-conformance, and by our own ADR-0012.** The honest option set is always *how tight a best-effort*, and **never** *best-effort vs. complete*.

## Revisit trigger

Only a change in the **fault model** reopens this — e.g. if a Realization is constrained to a provably bounded state space that a W-method-style argument could exploit. Absent a white-box state bound on the Realization, the residual stands. A divergence discovered in the field is **not** a revisit; it is a supersede that grows the sample (ADR-0012), leaving this decision intact.
