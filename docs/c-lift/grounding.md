# Grounding: lifting Spacewar 3.1 to matching C

## Goal (operator's words, binding)

Lift `source/spacewar3.1_complete.txt` (PDP-1 Macro assembly, 1962) to C that compiles back down to the byte-identical `build/oracle.rim`. Verification is the sha256 of the `.rim`, at every step. Constraints from the operator:

- No asm blocks, no inline assembly, no "this part stays asm". Every construct, including self-modifying code, gets a real C expression. The operator's position: there is an equivalent C for self-modifying code.
- No interpreter, no emulator inside the C. Interpreting the binary makes it a port, not the same game.
- Same binary means same game. The C is computationally equivalent because it compiles to the identical binary.
- The C should be human-readable C. It is not expected to look like anything the 1962 authors would have written (C didn't exist).
- The compiler is ours to build. Nothing like it exists. That is the point of the project.
- Guidance from the masswerk "Inside Spacewar" pages (`source/masswerk/*.html`) is fine as a reading aid. Ground truth is the source and the binary.

## Facts about the oracle

- `tools/oracle.sh` builds `build/macro1` from `tools/macro1.c` and assembles the source with `macro1 -r -d`. Output: `build/oracle.rim`, `build/oracle.lst` (listing with addresses, words, and symbol table). sha256 `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
- RIM format: macro1 punches a loader, then blocks of words with checksums, then a start jump. Same words at the same addresses in the same emission order give the same tape. Gaps (`. 200/`, `variables`) are not punched.
- Literals `(x` go into the pool at the next `constants` directive. Pass 2 dedups by value, and the pool order is order of first appearance. So the order in which literal values first appear in the emitted Macro text matters. One `constants` block in this program, at 02767.
- Variables `\x` are allocated at the `variables` directive (03223..03275), not punched. Their addresses appear inside instruction words, so their allocation order matters (check `tools/macro1.c` for the exact rule).
- PDP-1 CPU semantics: `ref/pdp1_cpu.c` and `ref/pdp1_defs.h` (open-simh). 18-bit ones' complement words, 4096-word core, AC and IO registers, 6 program flags, sense switches, test word. Instruction format: 5-bit opcode, indirect bit, 12-bit address. Operate and skip groups combine microcoded bits.
- The pipeline can be: our compiler emits Macro text, macro1 assembles it, and the hash is compared. A natural incremental scheme: the build splices compiled C output into the original source in place of each lifted routine's region, so untranslated regions stay as the original text until lifted. Every step must keep the hash.

## Source map

Line numbers in `source/spacewar3.1_complete.txt`.

- 1-61: macro definitions (`senseswitch`, `init`, `index`, `listen`, `swap`, `load`, `setup`, `count`, `move`, `clear`).
- 67-69: jumps at 3, 4, 5 (start vectors: sequence break, start at 4, start at 5).
- 77-96: tunable constant table at 6..31. Most entries are *instructions* (`law i 41`, `sar 4s`, `scl 9s`) executed with `xct`. `ran` is the PRNG state.
- 104-107: `cwr` control word routine slot at 040, space reserved.
- 112-116: `sbf` sequence break flush.
- 118-187: more macros (`xincr`, `yincr`, `dispatch`, `dispt`, `scale`, `diff`, `random`, `ranct`).
- 195-254: `sin`/`cos` (Adams Associates). 260-301: `imp`/`mpy` (BBN multiply). 309-343: `sqt`. 351-396: `idv`/`dvd` (BBN divide).
- 398-507: `oc` outline compiler. Compiles ship outline tables into PDP-1 code at runtime.
- 510-561: `blp`/`bpt` central star display.
- 565-653: `bck` background star display; the `dislis` macro is instantiated 4 times with different labels.
- 663-941: main loop (`ml0`..), game start/restart logic (`a`, `a1`, `a40`, `a2`..), control word getters `mg1`, `mg2`.
- 950-983: `mex` explosion. 987-1005: `tcr` torpedo. 1012-1077: hyperspace `hp1`, `hp3`.
- 1081-1309: `ss1`/`ss2` spaceship calc (gravity, thrust, display via compiled outline, torpedo launch, hyperspace entry).
- 1317-1333: `pof` ship in star. 1338-1357: outline tables `ot1`, `ot2`.
- 1360-1365: `constants`, `variables`, patch space, `mtb` object table (uninitialized, after patch space).
- 1371-1869: star catalog at 06077 (`mark` macro data, decimal), 4 groups `1j..1q` .. `4j..4q`.

## Machine idioms the C must express (no asm)

1. Subroutine entry by `jda` (AC stored into the entry word, return address in AC) or `jsp` (return address in AC). Callee immediately does `dap X` to patch its own return `X, jmp .`. Return via that patched jump or `jmp i`.
2. The jda entry word doubles as storage: the argument lives there and the cell is reused as a working variable (`sqt` reuses it as the remainder; `sin`/`cos` write each other's entry words).
3. `cos` adds pi/2 and jumps into the body of `sin` past its prologue, sharing `sin`'s patched return `csx`.
4. Inline arguments after the call. `jda mpy` / `lac B`: the callee executes the caller's next instruction with `xct` to fetch the second operand, then returns to call+2 via `idx`. `jda oc` / `ot1`: the next word is a table address read indirectly. `imp` executes its caller's inline instruction and then calls `mpy` with a twist.
5. Pointers held in the address fields of instructions. `init ml1, mtb` patches `ml1, lac .`; `idx ml1` advances it; `lac i ml1` dereferences through the instruction word; `index` compares against a literal instruction word `(lac mtb nob` as the loop bound. Dozens of parallel pointers (`mx1`, `my1`, `ma1`, `mb1`, `mom`, `mth`, `mot`, `mco` and `\m*` variables) walk the parallel object table arrays in lockstep.
6. Object table entries hold calc-routine addresses (`ss1`, `tcr`, `hp1`, `mex`), sometimes with the sign bit set as a "does not collide" flag (`mex 400000`). The main loop calls through them: `lac i ml1` / `dap .+1` / `jsp .`. Zero means slot empty.
7. Tunable constants that are instructions, executed via `xct` (`xct tvl` applies `sar 4s`; `xct tno` loads `-41`). Comments say they "may be replaced by jda or jsp".
8. Runtime code generation: `oc` writes instruction words (from literal instruction encodings like `(lac \sx1`, `(dpy-4000`) into memory starting at `nnn`, the ship code is reached by patching `sp5, jmp .`, and the generated code jumps back to `sq6`.
9. Jump tables via the `dispatch` macro (`add (. 3` / `dap . 1` / `jmp .` followed by `jmp` entries).
10. Unrolled code from `repeat` (`mus` x21 in `mpy`, `dis` x22 in `dvd`, `starp` x16 in `bpt`), and a 4x instantiated macro (`dislis`) producing four structurally identical copies of a routine with different labels and constants.
11. Busy-wait to burn the rest of the frame: `count \mtc, .`. Timing is part of the game.
12. Hardware: `dpy` (display point, AC=x, IO=y), `iot 11` (control boxes), `tyi`, `lat` (test word switches), `szs` (sense switches), program flags `stf`/`clf`/`szf`, `hlt`, `lsm`, `ioh` (wait for completion).
13. Ones' complement arithmetic with -0, combined 36-bit AC:IO shifts and rotates (`rcl`, `rcr`, `scr`, `scl`, `swap` = `rcl 9s` twice), multiply/divide steps `mus`/`dis`, combined skip microinstructions (`sma+sza-skip`, `spq`, `szm`).
14. Instruction encodings used as data and data used as instructions: `and (add 340` as a mask, `sad (lio Q+2` comparing a patched instruction against a bound, `ior (scl` building a shift instruction at runtime in `mex` (`mi1`) and then executing it.
15. Shared exits and fall-through between routines (`jmp csx-1`, `jmp flo+R+1`, `ss1` jumping into `sr0`).
16. Code placed at fixed absolute addresses (`3/`, `40/`, `6077/`), patch space, and uninitialized tables after the code.

## What "verifiable at each step" means here

The `.rim` hash gate is the only verdict. A step is one region of original source replaced by compiled C output, with the hash unchanged.

A known failure mode: a "compiler" that ignores the C and emits memorized assembly would pass the hash and prove nothing. The compiler must be a real compiler: its rules are general lowering rules over C constructs, and the C must mean what the binary does. How to keep the compiler honest (for example a compiler test suite of non-Spacewar C programs whose PDP-1 output runs in SIMH against expected results, or `gcc -fsyntax-only` against a header that gives every builtin a C reference definition) is part of the design.

## Seed observations (not requirements)

These came up while reading. Candidates may adopt, change, or reject them.

- The PDP-1 is an accumulator machine. Expression trees evaluate naturally in AC, so `x = y + z` lowers to `lac y / add z / dac x`. Operand order in C can carry choices the original authors made by hand (`law 1 / add ml1` vs `lac ml1 / add (1`).
- C's `register` storage class could mean "lives in IO".
- A function whose body is a single machine operation could be emitted as one word and invoked with `xct`. That gives idiom 7 a C form.
- `return f(x)` as a tail call could lower to the shared-exit trick in idiom 3.
- A pointer local could be homed in the address field of the instruction that dereferences it (idiom 5).
- C function pointers and a struct or bitfield over the table word could express idiom 6.
- A header (`pdp1.h`) could define the `word` type, 36-bit pair type, and hardware builtins, each with a reference C definition so the C has meaning independent of our compiler.
- pycparser (Python) is an option for the front end; `uv` and Python 3.14 are installed. gcc is installed.
