# The oracle is a characterization suite, not a reimplementation

**Amended 2026-11-15.** The oracle is the original binary (user, 2026-11-15); the checks against SIMH are evidence on the way to it.

Status: amended by ADR-0017 (the checks are the suite; the RUNS text, not a Realization, is what they check). Previously: accepted

We verify the RUNS realization against an **Oracle**: a suite of tests whose expected
values are *observed* from the original PDP-1 assembly (`source/spacewar3.1_complete.txt`)
executed on an instrumented emulator — never from a reference reimplementation, and never
from hand-reading the source. The original, executed, is the sole ground truth; masswerk is
a fallible **Translator** consulted only to interpret what a routine does; the emulator's CPU
semantics are **frozen** (instrumentation reads state and injects inputs, never altering how
an instruction computes).

## Why

The first conversion attempt *asserted* correctness and went unchallenged because nothing
could contradict it; a runtime later revealed bugs the source could not see. The two rejected
alternatives both reproduce that disease:

- **A reference reimplementation as oracle** is circular — you verify a port against a port.
- **Hand-derived expected values** just relocate the assertion one layer up, into the tests
  themselves. "Always be in doubt" is incompatible with trusting our own reading.

Executing the *original* is the only substrate where doubt terminates in something that cannot
lie to us. Emulating the original is not a "port" — it is the source running as itself.

## Consequences

- The Oracle is **deliverable zero**: it exists before any `.runs` Realization. A Realization
  earns its life by passing it.
- The Oracle is the *test suite*, not the emulator. The emulator produces observed values; the
  suite is what holds. (See `CONTEXT.md` → "Oracle ≠ Substrate".)
- "Done" for any Realization unit means **green against observed Ground Truth**, never "matches
  the Translator."
