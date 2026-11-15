# Spacewar's exclusion list

The original is the binary: `build/oracle.rim`, sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`, assembled from `source/spacewar3.1_complete.txt`. The RUNS source in `runs/` is its edition. The edition carries everything the binary does, and any departure is an exclusion stated here, with its exit point, its evidence, and who decided it (`../.github/CONTEXT.md`, Original, Edition, Exclusion, Exclusion list; `../runs-spec/README.md`, The binary is the original; the RUNS source is its edition).

## Exclusions

None.

## Why the list is empty

This is an inference from the evidence below, not a proof over every input.

- **Play reaches only the word's own arithmetic, and code the program fixes for itself.** `tools/reach_oracle.py` runs the binary in SIMH through seventeen scripted matches from the start address, with every sense switch setting and the full object table. Its report, `docs/reach-oracle.txt`, shows no jump to an unnamed place other than returns from a call, 730 sites of the word's own arithmetic, the halt on a full object table, reads of core the tape never loaded, and code the program writes from its own outline tables (`INTENT.md`, Where play reaches the machine in Spacewar). Each of these the edition carries: the arithmetic in the `word` type, the halt as `stop` in `launch_torpedo`, the power-on core as fields with no initial value, and the outline code as `outline_code` and `draw_outline`.
- **The one read past an array is unobserved.** The main loop reads past the ships' two-word outline array for every torpedo slot (`mot`, source line 865). `tools/check_frame.py 1500 poison` loads a jump to address 0 into `sp5` for every slot past the ships, and every frame still matches the evaluator. `tools/check_frame.py 50 poison-all` poisons the ships' slots too, and SIMH stops at once, so the check can fail (`INTENT.md`, Verified). Nothing the read loads changes the game, so the edition leaves no behavior of it unstated.
- **A player cannot give the program code.** What comes in is the console's switches, the control boxes or the test word, and the start address (`INTENT.md`, Spacewar's boundary so far). Code the player writes, the standard exclusion, has no way in.

## What the edition carries

The ones' complement arithmetic and the toroidal wrap that falls out of it; the fire glitch with sense switch 3 on; the halt when the object table is full; the central star's two random draws each frame; and the outline code the program writes for itself. The contents of core at power-on are an input. The pacing loop and the outlines are presentation, which the reference keeps whole.

## Who decided

The owner, approving the edition stance on 2026-11-15, which gives Spacewar's list as empty. The evidence above is the conversion's.

## Not yet checked

The edition's check, the rules run alone against the binary with differences allowed only at listed exclusions, has no tool yet (`todo.md`). Today `tools/check_frame.py 300 alone` compares the game with the presentation removed against the whole program, and binary identity covers the rest.
