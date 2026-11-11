# todo

## Round 1 (figure-it-out): port a slice, derive the intent
- [x] Slice ported and graded against SIMH (square_root, four calc routines, frame Network)
- [x] Functions removed; topology pure Petri (option a)
- [x] INTENT.md, docs/decisions.tsv

## Round 2 (feature): the reach tool, and the files brought up to what is settled
- [x] Data shape first: a Step per executed instruction (pc, AC, IO, effective address, op); places named by bound Record field, else listing variable or label
- [x] tools/reach_oracle.py over spacewar-c's 17 scripted matches; self-checks: copy of core vs SIMH, word arithmetic model vs SIMH's AC
- [x] Report saved: docs/reach-oracle.txt
- [x] Network contracts (reads:/writes:); top Network must declare its boundary; frame declares writes: display; mutation caught
- [x] pdp1.py: bind explosion_cloud.particles, square_root_call; note instruction-held fields; binding holds only what play cannot observe
- [x] RUNS sources annotated for the presentation split and power-on words
- [x] INTENT.md rewritten to what is settled; decisions.tsv rows
- [x] All checks re-run green
- skip: architect/arena for the tool: its shape follows SIMH's history format and the existing frame driver; nothing to choose between
- skip: a planted-defect test of the tool: every kind it reports except far jumps has a true positive in real play, and both self-checks compare against SIMH
- [ ] Open: a field-level classifier for gameplay vs presentation (by consequence) once more of the game is ported
- [x] Port the spaceship; play never observes mot's reads past the outline array (round 6)
- [x] The boundary's inputs: console (test word, control boxes), power-on score and game count, start address (round 5)
- [x] The sense switches the spaceship reads (round 6); switch 4 with the heavens (round 8)
- [ ] Open: runs-spec is untouched; it still says what the user called directionally right, wrong in details

## Round 3 (autonomous): compile multiply, divide, sincos from RUNS
- [x] multiply: RUNS mpy + imp Network, check_multiply vs SIMH, pdp1/multiply.toml, runsc networks/calls/byname/dword, MATCH, gate
- [x] divide: RUNS dvd + idv Network, division enum for the skip, check_divide vs SIMH, block/skips/io_param/cells in the binding, MATCH, gate
- [x] sincos: RUNS sin/cos Networks over mpy, check_sincos vs SIMH on all 2^18 words, exit-first loop layout + block_takes_entry, MATCH, gate
- [x] sincos saturation branch: no word of 2^18 reaches it (exhaustive run by hand, round 9); only the image gate covers the branch's code

## Round 4 (autonomous): compile tunables and objects from RUNS
- [x] tunables: all twelve xct tunables as Processors, the numbers as tunables fields; check_tunables vs SIMH; pdp1/tunables.toml with the machine's words (sequence break, start vectors, control word slot); XCT + ac_param, [names], MINUS_ZERO in runsc; MATCH, gate
- [x] objects: explosion, torpedo, in_hyperspace, breakout compiled from RUNS; RUNS reshaped where the original carries a register (diff's position, the dots' IO, hyperspace's IO, the jump's swap, a cla per diff); runsc: cursors, inline macros, pending AC results, Network guards/loops, bottom-tested loops, shared tail, shift homes, dpy, enum spelling; MATCH, gate

## Round 5 (autonomous): compile the main loop and game control from RUNS
- [x] RUNS: start Networks, frame, object_loop, between_games/ask/show_scores/new_match/new_game, control_word; score/console/controls/lights/scoreboard/outline_call/outline_space
- [x] Language: fields with no initial value come in (top Networks declare them); `wait`; several top Networks are one game
- [x] check_game.py vs SIMH: 3000 seeded cases, 17 scripted matches (51000 stops), control word; 14 mutations caught
- [x] pdp1/main_loop.toml + runsc rules (table, walk, cursors' homes, carry, stray, blocks, repeat, jumping guards, enum sign/zero tests, xor sharing, devices, flags, hlt+wait, clearing loop, dispatch); MATCH; gate 263/263
- [x] Confirmed with the spaceship port: play never observes the carried outline word (mot) for torpedoes (check_frame poison)

## Round 6 (autonomous): compile the spaceship from RUNS
- [x] RUNS: spaceship.runs (first/second_spaceship, spaceship, accelerate, after_outline, launch_torpedo), spaceship.runs-prim; records spaceship, pen, launch; console sense switches; handoff fields
- [x] Language: enums may share a member name (resolved by type); evaluator fix: a field's name is not a Record mention
- [x] check_spaceship vs SIMH: 3000 calls through the compiled outline (tools/outline.py stand-in); 17 mutations (14 caught, 1 after one-free-slot tables, 2 equivalent)
- [x] check_frame with flying ships: 1500 frames; poison mode for the mot verdict, with its control
- [x] pdp1/spaceship.toml + runsc rules (exit, back/pulse externs, carried homed jump, slot-field cursors and search, sense/flag guards, shared Network tail, pool-word dispatch); MATCH; gate 357/357
- [x] The outline compiler and outlines (presentation): ported in round 7; tools/outline.py deleted

## Round 7 (autonomous): port the outline compiler, the outlines and the core layout
- [x] Design: instructions as values of the machine description's type insn in a Record (outline_code), run by `jump` with the PDP-1's rules; compiler as a Network cut at the original's labels. Alternatives weighed: one Processor (cannot call ocs; its order is not the original's), raw words (would put macro1's pool addresses in the text)
- [x] Evaluator: type insn, instruction constructors, jump with contract and bound, initial values a slot, slots past a collection are errors, Network loop exit that runs things first
- [x] RUNS: outlines.runs, outlines.runs-prim; outlines, outline_code, outline_compiler Records; pen.saved_x/y; outline_space and the outline enum gone; frame contract without pen
- [x] Bindings: core_layout.toml, outlines.toml, outline_compiler.toml; [[code]] draw_outline; [into]; MATCH; check_compiled 423/423
- [x] check_outline_compiler vs SIMH (9 outlines, 6 ddd settings); 10 compiler mutations caught; check_spaceship/check_frame through the ported code; `moved` relocation; 5 machine-rule mutations caught
- [x] reach_oracle re-run: same findings, code space named outline_code
- [x] The heavens and the star catalog (round 8)
- [ ] Open: runsc's layout rules grow per unit (jump table, rotated loop); an independent review should judge whether each is general

## Round 8 (autonomous): port the heavens and the star catalog; every unit from RUNS
Playbook (autonomous run), verbatim:
- [x] 1. State the exit condition as a checkable predicate before the first iteration (tests green, repro fixed, all N PRs merged, pixel-diff zero).
- skip: 2. Pick the wake mechanism (loop skill): no external event to watch; every check runs in the foreground
- [x] 3. Each iteration makes the smallest change the evidence justifies, verifies it against the predicate, commits if it advanced, discards changes that didn't help.
- [x] 4. Mid-run discoveries are yours.
- [x] 5. Checkpoint every iteration via the show-me-your-work skill.
- [x] 6. Stop when the predicate is met.

Predicate: runsc MATCH 8744e9c9 with all 13 build/lift/*.c generated, none symlinked, and build/lift holding only generated files; check_compiled passes; check_heavens (central_star, expensive_planetarium vs SIMH, wrap paths, mutations) passes; check_frame runs whole frames; check_all.sh passes.

- [x] RUNS: central_star, star_line, star_slope, draw_star; expensive_planetarium, show_magnitude, move_window; star_catalog Record; sense switch 4
- [x] Evaluator check vs SIMH (check_heavens.py): seeded + edge cases + scan-wrap paths, 66/66 statements; 23 mutations caught
- [x] check_frame through the heavens (whole frames); poison patch moved to the patch space
- [x] Bindings pdp1/heavens.toml, pdp1/star_catalog.toml + runsc rules; MATCH; check_compiled 2365/2365
- [x] Remove bridges to lifted C ([names], [[extern]], includes, symlinks); build/lift holds only the 13 generated files; strace: no spacewar-c/lift file opened
- [x] deslop; docs (INTENT, pdp1/README, todo); decisions.tsv
- [ ] Open: runsc's layout rules for the planetarium (arms apart, exit_after, place comparisons) are shaped by one routine; an independent review should judge them
- [ ] Open: a full window cycle of the planetarium (2*16*020000 frames in a row) is not run; set-word frames cover the margins instead

## Round 9 (autonomous): close the review's holes in "the text holds the game, the binding no logic"
Playbook (autonomous run), verbatim:
- [x] 1. State the exit condition as a checkable predicate before the first iteration (tests green, repro fixed, all N PRs merged, pixel-diff zero).
- skip: 2. Pick the wake mechanism (loop skill): no external event to watch; every check runs in the foreground or a background job I wait on
- [x] 3. Each iteration makes the smallest change the evidence justifies, verifies it against the predicate, commits if it advanced, discards changes that didn't help.
- [x] 4. Mid-run discoveries are yours.
- [x] 5. Checkpoint every iteration via the show-me-your-work skill.
- [x] 6. Stop when the predicate is met.

Predicate: runsc MATCH 8744e9c9; the extended check_compiled passes (every mutant of numbers, field references, operators, statement deletion and adjacent swaps changes the image, is refused, or is evaluator-equivalent on seeded states); each reviewer mutant re-run is changed/refused/equivalent; check_all.sh passes on the final commit; findings 1-10 fixed or declined with a logged reason.

- [x] Gate: structural mutants + evaluator equivalence, every same-type field swap, every binding key live (findings 6, 7)
- [x] Dead binding keys gone; schema: unknown keys, missing keys and names that name nothing are errors (6)
- [x] runsc checks the program as the evaluator does, plus a static scope check; crashes are BindErrors (3)
- [x] Enum members resolved by the field's enum (4)
- [x] carry derived from draw_outline's jump; refused when the walk does not load it for every slot that jumps (1)
- [x] Shared words and registers: each RUNS read is of the name the word holds there, else a bit-level proof it is unused (2)
- [x] [share] (via shared words) and stray checked; skip return set on every path (5)
- [x] pdp1/devices.toml: sense switches, lights, start vectors in one place (8)
- [x] check_game: UNKNOWN in the evaluator where SIMH knows is a failure, but for the lights (9)
- [x] Docs: INTENT Verified, README contract, flush, saturation (10)
- [x] deslop, check_all on the final commit, decisions.tsv
- [ ] Open: no independent reviewer has re-read runsc's shared-words check and the bit-level proof (BLOCKED: independent review in this subagent)
- [ ] Open: the gate does not mutate a match's arms or insert statements; cross-type field swaps were swept once by hand (939, none silent), not in the gate

## Round 10 (autonomous): close reviewer C's holes
Playbook (autonomous run), verbatim:
- [x] 1. State the exit condition as a checkable predicate before the first iteration (tests green, repro fixed, all N PRs merged, pixel-diff zero).
- skip: 2. Pick the wake mechanism (loop skill): no external event to watch; every check runs in the foreground or a background job I wait on
- [x] 3. Each iteration makes the smallest change the evidence justifies, verifies it against the predicate, commits if it advanced, discards changes that didn't help.
- [x] 4. Mid-run discoveries are yours.
- [x] 5. Checkpoint every iteration via the show-me-your-work skill.
- [x] 6. Stop when the predicate is met.

Predicate: runsc MATCH 8744e9c9; reviewer C's harnesses (hC_gen, hC_gen2, hC_decl, hC_bfuzz, hC_elem) re-run at HEAD show 0 silent-and-different, 0 crashes, every declaration drop caught; the extended check_compiled passes; check_all.sh passes on the final code commit; findings 1-6 fixed or declined with a logged reason.

- [x] 1. "One value in two places" peephole sound; every other runsc peephole audited for unchecked assumptions
- [x] 2. Gate: dup, move, insert, run target, negate, branch swap, match arms, cross-type/record field, declaration drops, binding list elements and values
- [x] 3. runs.check: declarations checked against bodies both ways; requires decided
- [x] 4. runs.check: static types
- [x] 5. runsc crashes become BindErrors at their cause
- [x] 6. Dead list element handoff.swap; the gate catches dead list elements
- [x] deslop, docs, decisions.tsv, check_all (972027f: full gate 39,847 mutants and check_all pass)
- [x] Audit (subagent) of every runsc peephole: two more holes fixed (a block's run in tail position; the jump-back run's arguments); loop bounds kept as RUNS's check, judged by firing
- [ ] Open: the audit's rules judged unchecked but guarded by the image in practice (held guards, shared xor, spill, preinc, shift-table `known`, jump-table range, pending results, slot chain) have no mutant that builds MATCH; no rule makes them sound by construction
- [ ] Open: no independent reviewer has re-read this round's runs.check type and declaration rules (BLOCKED: independent review in this subagent)

## Round 11 (fix wave): close reviewer D's holes
- [x] 1. runsc dispatch: an arm's run passes the scrutinee's slot; gate kind `argument`; audit (subagent) of every pattern match: match coverage, word operator arity, statements after a jump out, now runs.check errors
- [x] 2. Unused parameters and locals rejected; place_torpedo's slot gone; sine_answer's dropped half is `_`
- [x] 3. Static checks: ordering compares, 18-bit numbers, constant slots, break/continue placement, constant compares, return without a value
- [x] 4. outline_code's count reserved after the table; the star catalog follows it (no `at`)
- [x] 5. INTENT: bounds are RUNS's checks, not proofs; the twelve bounds listed
- [x] 6. Every initial value mutated; a silent one judged by 60 games from power-on
- [x] Evaluator: a bound that fails to evaluate stops the firing at the bound
- [ ] Open: runs-spec's check_examples fails two examples under the stricter checks (DIGS #8 now rejected for its ordering compare; NETWORK_TOPOLOGY's size_cloud never reads its slot); runs-spec is outside this round
- [ ] Open: audit's latent miscompiles (with_operand vs rotated_operand; held guards) have no MATCH mutant; no rule makes them sound by construction

## Round 12 (figure-it-out): convert Spacewar into pure RUNS

Standing orders: `CLAUDE.md`. Decision trail: `docs/decisions.tsv`, phase `pure-*`.

Playbook (figure-it-out), verbatim:
- [x] Read the Principles section of the poteto-mode skill.
- [x] Phase A: Frame. Definition of done as a falsifiable predicate; scope quantified; rigor level.
- [x] Phase B: Design the workflow. Atomic units, riskiest unknown first, verification harness before the work.
- [ ] Phase C: Run the loop. Each unit an experiment: hypothesis, smallest change, measure against the predicate, keep or revert.
- [ ] Phase D: Keep the audit trail (show-me-your-work): a decisions.tsv row as each step lands.
- [ ] Phase E: Verify and hand back against the predicate, on the real product.

### Predicate (done)

Every Record of `runs/` has a kind; `tools/check_purity.py` reports 0 (so `runs.check` enforces the kind rules on Spacewar, with no exception left); the Network is in the form settled below; `runsc` prints MATCH 8744e9c9; `tools/check_all.sh` passes; `tools/check_frame.py N alone` (in check_all) shows the game with every presentation routine and Record removed firing the same as the whole program on every kept Record, while the whole program matches SIMH; the same mode for check_game's cases.

### Scope (measured 2026-11-09)

31 Records, 133 Processors, 30 network blocks. Purity report at the start: 37 = 31 Records with no kind + 6 items of code kept as data (outline_code.insn, outline_compiler.start_over and .to_other_side, handoff.swap and .pending, draw_outline's jump). Giving the Records kinds will reveal the Processors that touch game and presentation Records; `--against` allows exactly those new lines.

Mixed Records to split before they can take one kind: `ships` (outline is presentation), `frame` (spare_time is pacing), `tunables` (separate_outlines is the outline's), `handoff` (26 register carries of every concern, bound as one register Record in main_loop.toml), `spaceship` (game values and the flame count beside each other).

### Rigor: high

Every commit keeps MATCH and check_all; `check_purity.py --against HEAD` passes; a compiler change is a rule a second PDP-1 program would use, with a row naming the idiom; a new check is proven by a planted defect.

### The riskiest part: the Network's form (settled)

The Network is derived from the game's logic, which in a conversion is the original program: its order is read off the original's code, and the text records it. The first framing of this section set that against the EGS overview's "derived, not authored", reading "derived" as "computed from reads and writes" and "authored" as "written in the text". That was a misreading: writing down the order the original runs is deriving it, not authoring it. What remained was purity on the Network side, now settled: each line break is a place passing the turn, a guard only tests values Records hold, a `run` passes only the slot.

The hardest compile sites after it: the outline (logic kept as instructions in a Record; the image holds the outline compiler and the jump into its output, so a pure walker must compile to "compile at each new game, jump each frame" under a rule a second PDP-1 program would use), and `handoff` (splitting its carries by kind means several Records sharing one register, which touches every unit).

### Phases

0. [ ] Scaffold and decide. (a) [x] `runs.without_presentation` and `check_frame.py N alone`: proven red on a copy with pen and display typed presentation (exhaust's fuel, the explosion's count and the random draws go with the drawing). [ ] The same mode in check_game. (b) [x] Anchors: a stream is presentation, so its emitters are; instructions in a Record and `jump` are impure in every program. (c) [x] The Network's form: settled. The order is stated in the text (each line break is a place passing the turn), guards only test, `run` passes only the slot. The order is read off the original's code (collision and calc both write objects, so reads and writes alone cannot give it; 294/300). breakout's guard converted, MATCH with runsc unchanged.
1. [x] Spike the outline in the settled form. At least two pure shapes (a walker over the outline codes; a presentation Record of expanded steps that a walker plots); for each, what runsc must emit for oc, the free-core layout and sp5. Bar: a rule a second PDP-1 program would use. Done when one shape compiles to MATCH with check_spaceship and check_frame passing, or the evidence that none can is in front of the user.
   Done 2026-11-10 by the held-as-code rule (`docs/rules/held-as-code.md`): one rule, two sizes, the arms compiled by runsc's statement compiler as C `TEMPLATE`s and by pdp1cc's selector, no second selector. [x] Rule doc. [x] Minskytron and the explosion through it, `[homes] "instruction"` deleted. [x] The outline: 302b767's pure text, compiled with the rule plus cross-jumping (`tails = "shared"`, DDT and the music player as second programs) and the JSP store routine (the music player's `put`); MATCH, check_all, purity 46 gone 0 new. [x] Proof: a planted arm defect turns check_outline_compiler and check_game red; check_compiled mutates the arms (3980 mutants, 0 silent). [x] Review fixes (independent review, "mostly general"): the jump word and the store run come from pdp1cc's compiled words, `times` gone; `pulse` from the binding; pdp1.py's second encoder and the jump table's dead first arm deleted. Spacewar-only, said in the rule doc: the run size, and one store call laying out a repeated word. Borderline binding keys left as placement: `loaded`, `pulse`.
2. [ ] Harden the compiler. Review runsc's rules for ones shaped by a single routine (pdp1/README.md, the open items of rounds 8-11) and fold them into general PDP-1 idioms, gated by check_compiled and MATCH. Done when every rule has a decisions row naming its idiom, or is gone.
3. [ ] Give every Record a kind, splitting the mixed Records above. Data shape first: Record and field changes, the `reads:`/`writes:` they force, and the binding's lists (`pool`, `registers`, `[share]`); no change to what any Processor computes. Done when the report lists no Record without a kind.
   Partly done 2026-11-10 (purity 47 -> 30): [x] `pacing` (spare_time, presentation) out of `frame` (game). [x] Typed with no split: objects, random, score, console, controls, lights interface; scoreboard presentation; spaceship (flame burns fuel, so game whole), launch, the call Records game. [x] `explosion_count` (particles, game) out of `explosion_cloud`. [ ] Blocked until Phase 4 converts exhaust and the explosion dots (decisions row "Phase 3 stops"): 14 Records untyped; typing any presentation Record a display emitter touches turns `check_frame alone` red, and the handoff, tunables and ships splits each add a presentation Record that must be typed in the same commit. ships also needs the table's column order in the binding. Typing all of them switches `runs.check` on with 24 impurities left.
   Done 2026-11-10 but for one Record (purity 30 -> 21): [x] handoff split by kind (game handoff; presentation explosion_dot, outline_reading, outline_point), with the runsc rule for a register field cleared in an AC operate's word (DDT's listen the second program). [x] tunables split (outline_setting presentation). [x] ships split in the table's order (ship_flight game, ship_outlines presentation, ships game). [x] Typed presentation: display, explosion_cloud, pen, magnitudes, central_star, planetarium, star_catalog, outlines, outline_code, outline_call, outline_compiler. [ ] tunables (game) stays untyped: typing the last Record switches `runs.check` on, which refuses the text while impurities are left; it is typed in the commit that brings the report to 1. [x] clear_tables no longer clears the presentation's ship_outlines.outline: runsc rule (a), approved by the user, lets the one clearing loop clear a table field whose old value it proves dead (the Macro assembler the second program; rows pure-3).
4. [x] Convert interaction by interaction, from the report: [x] exhaust, [x] explosion dots, central star, spaceship outline aim, planetarium, spare-time pacing, the handoff carries, the scores and lights. Each per CLAUDE.md's steps. Done when the report reads 0.
   Exhaust and explosion dots done 2026-11-10 (rows pure-4): the count, the fuel and whether the rocket fires are game Processors run by network exhaust and the explosion Network; the spread, the flame's steps and the dots are presentation; heading (sine, cosine) and explosion_count are interface. runsc: a bottom-tested loop's early breaks jump past it. Probe with display, explosion_cloud, pen, magnitudes typed and drawing_handoff (particle_low, pen_x, pen_y) split from handoff: check_frame 100 alone 100 match. The cli's game-side IO field landed with the handoff split. Left (the mixed Processors): plot_torpedo (emits the game's handoff.position, the x diff leaves in AC), aim_outline (reads the game's spaceship.nose_x/nose_y), and the 16 Network lines.
   Done 2026-11-10 but for one line (purity 19 -> 2, rows pure-4): [x] the scores switch (ask, show_scores: read_scores_switch into handoff.scores_switch). [x] the hyperspace buttons (after_outline: hyperspace_buttons into handoff.hyperspace_buttons, inside the jumps-left guard). [x] the outline's aim: the nose is the interface Record ship_nose. [x] plot_torpedo plots objects.x[slot]; runsc: a call's result stored last is that word's value next (Minskytron's step_a/plot_a). [x] the planetarium: show_magnitude(m), its ranges and intensity constant fields of magnitudes; runsc: a collection field no routine sets is a table of constants (hc1d's copy macro). [ ] Blocked: the restart check's guard (frame.runs:34, `1 + torpedoes < 0`). Every pure shape needs the second torpedo test spelled `spa i; jmp mdn` (its own skip, i flipped) where runsc spells `sma`; the rule that does it (an if whose else is one jump: the test jumps there on its failure) compiles to MATCH, but `spa i`/`sma i` before a jump occurs in no PDP-1 program of the corpus but Spacewar (3.1, 4.1f, 4.4, the same md1 code), so it waits for the user. [ ] tunables stays untyped until that line goes (typing it switches runs.check on).
   Closed 2026-11-11 (purity 2 -> 0, rows pure-4): [x] the restart check: the game Processor torpedoes_left(ship) into handoff.torpedoes_left, the second test spelled by the one declaration the user approved (`[inverse_skip]` in pdp1/main_loop.toml, count +1). [x] tunables typed game (every reader a game Processor). [x] The migration exception is gone: runs.check refuses every impurity, an untyped Record among them, on every program. [ ] Open: runs-spec still says the loader enforces the kind rules only on a program whose Records all have kinds (NETWORK_TOPOLOGY.md, CONVERSION_PROCESS.md, README.md, DIGS_EXPRESSION_LANGUAGE.md); its examples pass with the new runs.py.
5. [ ] Close: check_game_alone in check_all; spec and INTENT match what was done; the viewer redrawn as a transcription of the pure text; independent review.

### Decisions for the user

- [x] The binding is retired (pure-5): `pdp1/*.toml` are the PDP-1 package's declarations, which only shrink (`tools/check_declarations.py`, `pdp1/DECLARATIONS`). Open: audit them (what the text can state moves to the text; what a general rule derives is deleted); move the drawing-only ones into the presentation text.

- [x] The Network's form: settled (runs-spec README "The order is in the text"); the only form the constraints allow.
- [x] `jump`: impure in every program; a general compiler emits code-as-data from pure RUNS.
- [ ] The viewer lays the net out with its own grouping; it becomes a transcription once the Network's form is settled.
