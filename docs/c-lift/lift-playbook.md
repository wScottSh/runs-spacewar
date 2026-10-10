# Lift playbook

Every milestone of the lift follows this file. Read it in full before starting a milestone.

## The goal and the finish line

Spacewar 3.1 (`source/spacewar3.1_complete.txt`) becomes human-readable C under `lift/`. Our compiler, `tools/pdp1cc`, lowers that C to Macro text, and macro1 assembles the text into a `.rim` byte-identical to the oracle (sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`).

The run is done when all of these hold:

1. `pdp1cc build` produces the oracle hash from `lift/` alone. Every word of the image comes from compiled C, and no line of the original source is spliced in.
2. `pdp1cc gate` is green. This covers the corpus (G2), the lint and isolation check (G3), the hint-deletion gate (G5) and the prediction edits (G6).
3. Every reference check is green: each pure routine is compared, native build against SIMH running the oracle, over its full input domain or a stated sample.

## Non-negotiables (from the operator)

- No asm blocks, inline assembly, raw-word escape hatches, or "this part stays assembly". Every construct, including self-modifying code and runtime code generation, gets a genuine C form.
- No interpreter or emulator, in the output or in `pdp1.h`. The reference build never executes generated PDP-1 code.
- The compiler is a general compiler. Rules are lowering rules over C constructs. Never write a rule, table, or special case keyed to a Spacewar routine, symbol, address, or word. G3 enforces part of this, and judgment enforces the rest. A rule whose only user is Spacewar code needs a non-Spacewar corpus program using it before it lands (G7).
- Same binary means same game. The hash is the verdict.

## Naming: use the masswerk concepts

Name C functions, variables, types, and fields after the concepts in Norbert Landsteiner's "Inside Spacewar!" (`source/masswerk/*.html`). Read the page for your region before naming anything. Examples of the vocabulary: object table, calc routine, outline compiler, outline, central star (the "sun"), heavens / Expensive Planetarium, gravity, hyperspace (hyperspatial uncertainty, breakout, recharge), torpedo, torpedo space warpage, explosion, collision, control word, sense switches, test word, main loop, frame timing / spare-time loop, sequence break, scores.

- The C identifier is the readable concept (`square_root`, `object_table`, `outline_compiler`). The original Macro symbol goes in a comment on the definition, so a reader can cross-reference the listing.
- The compiler generates Macro symbols itself. A long C name gets a generated symbol, and files link by C name: a name of external linkage is one symbol in every file. (Until M8, `SYM("x")` pinned a symbol that unlifted original text named. M8 removed it with the last unlifted line.)
- Short comments say what a thing means in the game, in masswerk's terms. Don't narrate instructions.

## Workflow per milestone

1. Branch from up-to-date `master`: `git switch -c lift/<milestone>`.
2. Read `docs/grounding.md`, `docs/design/synthesis.md`, and `docs/design/candidate-3/{rationale,compiler}.md`. The rationale's "Implementation reconciliation" section is the current contract. Read the existing compiler before extending it.
3. For each construct you need, add the rule. Add corpus programs first (G7): at least two non-Spacewar programs per new rule, run in SIMH against the native reference.
4. Lift the region's C into `lift/<name>.c` and add it to `lift.toml`. `uv run pdp1cc build lift.toml` must print MATCH.
5. For pure routines, add a reference check (native g++ build of the lifted C vs SIMH running the oracle `.rim`), over the full domain when it is at most 2^18 inputs, otherwise a seeded random sample of at least 100k plus edge cases.
6. Run everything: `uv run pdp1cc build lift.toml`, `uv run pdp1cc gate`, `uv run python tools/check-g3.py`, `uv run python -m unittest discover -s tests`, and every `tools/check-*-reference.py`. All green.
7. Make a mutation sanity check: change one operator or constant in the newly lifted C, confirm the build reports a mismatch at the expected place, then revert.
8. Update the design's Implementation reconciliation section with every new rule and every deviation, and why.
9. Commit in small verified steps. Messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Push the branch and open a PR to `master` with `gh pr create`. The body states what was lifted, the new rules, the check commands and their output, and the lifted-coverage number. It ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Do not merge. The orchestrator verifies and merges.

## When the design doesn't fit

If a construct needs more than a local extension of the design, stop and report it instead of bolting on a special case. Repeated workarounds of the same shape mean the design is wrong. The orchestrator re-runs design for it.

## Milestones

| id | region(s) | brings |
|---|---|---|
| M1 math | imp/mpy, idv/dvd, sin/cos (lines 190-396) | BYNAME inline operands and `idx R` placement, unrolled `repeat` (octal counts), tail-call/BLOCK shared exits, labels inside bodies, `dio`, coverage report |
| M2 tunables | constant table 3-116 (start vectors, tunables, cwr slot, sbf) | XCT one-word functions, `AT` origins, reserved space, hardware builtins |
| M3 outline compiler | oc (398-507), outline tables ot1/ot2 | runtime code generation as data plus jump, `insn` constructors, dense-switch dispatch, ENTRY_CELL |
| M4 heavens | blp/bpt (510-561), bck and dislis ×4 (565-653), star catalog (1371-1869) | Duff's device, instantiated routines, decimal data tables |
| M5 objects | mex, tcr, hp1, hp3, pof (946-1077, 1312-1333) | runtime-built shift instruction, homed pointers via `i ma1` and friends, POOL |
| M6 spaceship | ss1/ss2 (1079-1309) | JSP through `cwg`, gravity, thrust, entering the compiled outline, torpedo launch |
| M7 main loop | ml0..mq3, game control a..a6, mg1/mg2 (663-941), constants/variables/mtb (1360-1365), macro prelude | HOMED cursors over the object table, indirect calc calls, build from `lift/` alone |
