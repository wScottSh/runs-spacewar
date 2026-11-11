# The RUNS port and its compiler replace the JS Oracle harness

**Amended 2026-11-11.** This ADR calls the RUNS text "the RUNS port", the PDP-1 declarations "a PDP-1 binding", and `tools/runs.py` "a reference evaluator". In EGS terms the RUNS text is a conversion, not a Port, which swaps Realization Processors under an untouched Rules region (`../.github/CONTEXT.md` 313-339); "binding" is retired for the declarations (`CONTEXT.md`, Declarations); and a reference implementation is a body blessed by ID on the commons (`../.github/CONTEXT.md` 466-474). Its decision is unchanged. The vision governs.

Status: accepted (supersedes ADR-0009, ADR-0012, ADR-0013, ADR-0015 and ADR-0016; amends ADR-0001, ADR-0003, ADR-0004, ADR-0005, ADR-0006, ADR-0008, ADR-0010, ADR-0011 and ADR-0014)

The game is now written in RUNS (`runs/`), and a reference evaluator runs it (`tools/runs.py`). A compiler (`tools/runsc.py`) builds the RUNS text, with a PDP-1 binding (`pdp1/`), back to the original tape image through spacewar-c's `pdp1cc`. `pdp1cc` compares the image's sha256 with the hash pinned in spacewar-c's `lift.toml`. spacewar-c's `tools/oracle.sh` assembles Ground Truth with `macro1` and asserts the same hash. The checks (`tools/check_*.py`) fire each RUNS Network in the evaluator and compare it with Ground Truth running in SIMH, through spacewar-c's SIMH driver (`pdp1cc.gate.simh`). The JS Oracle harness (`oracle/*.js`, the coverage gate and its manifest, the Portable Oracle and `decode.js`, the per-routine vector manifests, the old build scripts under `tools/`) is removed. The vector files the checks still read stay in `oracle/`. The removed files are in the history at the parent of commit 9d24f9c.

## Why

ADR-0016 split the game logic into a Conversion that could not execute, because no DIGS evaluator existed, and a Realization that could. ADR-0016 named an evaluator as its revisit trigger. Both premises changed. RUNS has an evaluator, so the RUNS text executes and is graded directly against Ground Truth. And the RUNS text compiles to the original image, so the hash grades the whole of it at once. Grading a Realization through an address-free Portable Oracle (ADR-0015) is no longer the path. The checks read Ground Truth's core as Records through `tools/pdp1.py`, which names the Macro symbol where each Record field lives.

## What still holds

- **ADR-0001.** Expected values are observed from Ground Truth executed in SIMH, never from a reimplementation. Every check that compares behavior runs SIMH, except `check_square_root`, which reads vectors recorded from SIMH. `check_sincos` also compares with its recorded vectors. The Oracle as a suite, and the Realization it graded, are gone. The checks are the suite now, and the RUNS text is what they check.
- **ADR-0003 and ADR-0005.** SIMH and `macro1` are the Substrate and the Assembler, and SIMH is built without the Type 30 display. Both are built in spacewar-c (`tools/build-simh.sh`, `tools/oracle.sh`) with `gcc` on Linux, not with MSVC on Windows.
- **ADR-0004, in part.** `square_root` is checked over its whole domain (65,536 inputs). The sin and cos vectors cover all 2¹⁸ inputs, and `check_sincos` runs all of them by default. `check_all.sh` runs a 20,000-input sample. The branch-coverage bar for the other regions went with ADR-0012.
- **ADR-0007.** The domain is the game's. The checks draw their inputs from what play reaches, plus edge cases.
- **ADR-0008, in part.** The recorded vectors stay raw octal words. Only `sqt` keeps a provenance file (`oracle/provenance.json`), and no tool reads it. The manifests that held the other routines' provenance are at `9d24f9c^:oracle/*-manifest.json`.
- **ADR-0010, in part.** No OS is canonical in principle. In practice one Linux build is the only one, and no second environment witnesses it.
- **ADR-0011.** "Verified" is an objective artifact gate. Here the gate is `tools/check_all.sh`: the image's hash, a sampled mutation check (`check_compiled.py --sample 8000`; the full check runs by hand), and every check against SIMH. It needs spacewar-c beside this repository. No CI runs it.
- **ADR-0014, the impossibility only.** No finite suite proves equivalence. The port's equivalence judgments and its loop bounds are evidence, not proof (`INTENT.md`, "Verified"). The Portable Oracle's projection rules in ADR-0014 went with ADR-0015.

## What changes

- **ADR-0006.** The witness for assembly is the image hash, not the listing ↔ core cross-check, which no tool runs now. spacewar-c assembles Ground Truth with `macro1`, and the compiled RUNS must produce that exact image.
- **ADR-0009.** Superseded. Its sanity properties for `sqt` (monotone, √0 = 0, perfect squares, manifest complete) are no longer checked. `check_square_root` checks the input count and that every vector matches.
- **ADR-0012 and ADR-0013.** Branch coverage is no longer the definition of done. The definition is a hash match, each Network matching SIMH, and the mutation check (`tools/check_compiled.py`). The mutation check requires every edit to the RUNS text or the binding to change the image, be refused, or be shown to leave the game the same.
- **ADR-0015 and ADR-0016.** Superseded, for the reasons above.

ADR-0002 is not in this directory. Commit 507a6c1 deleted it and kept its decomposition principle in ADR-0012.
