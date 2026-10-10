# spacewar-c

Spacewar! 3.1 (MIT, 1962), lifted from PDP-1 assembly into readable C that compiles back to the original binary, byte for byte.

The C is not a port. Our compiler, `pdp1cc`, compiles it to PDP-1 machine code. The result is the same paper-tape image the original assembly produces, with the same instructions at the same addresses. Same binary, same game.

```c
JDA word sqt(word r)                /* r is the entry word: input, then remainder */
{
    sq1 = -023;                     /* isp counts up to 0: 022 (18) passes, 2 bits each */
    sq2 = 0;                        /* root so far */
    register word lo = r;           /* low half of the 36-bit AC:IO shift register */
    r = 0;
    for (;;) {
        if (++sq1 >= 0)
            return sq2;
        ...
```

That is the integer square root routine (`lift/sqt.c`). Compiled by `pdp1cc`, it becomes the 32 words at octal addresses 00246-00305 of the original image.

## Status

The lift is complete. `pdp1cc build` compiles the C in `lift/` into the whole image: all 2514 words come from compiled C, and no line of the original assembly takes part. The original source stays in the repository only as the input of the oracle build.

Milestones are listed in [the lift playbook](docs/lift-playbook.md). Decisions and their evidence are logged in [`docs/decisions.tsv`](docs/decisions.tsv). The design, and every place the code departs from it, is in the [rationale](docs/design/candidate-3/rationale.md) under "Implementation reconciliation".

## How the lift works

1. `tools/oracle.sh` assembles the original source, `source/spacewar3.1_complete.txt`, with `macro1`, the PDP-1 Macro cross-assembler from open-simh simtools. The output, `build/oracle.rim`, is the oracle. Its sha256 is `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
2. `pdp1cc build` compiles the files that `lift.toml` lists, in that order, into one PDP-1 Macro program. The order is the order of the words on the tape. A C name that two files share is one Macro symbol in both. The compiler writes the program's title line and ends it with the start address, which the C names with `START`.
3. The build assembles that program with the same `macro1` and compares the sha256 of the `.rim` with the oracle.

The C is written in a small dialect defined by `tools/pdp1cc/include/pdp1.h`. The PDP-1 has two registers, AC and IO, and the dialect maps C storage onto the machine:

- An automatic `word` lives in AC.
- A `register word` lives in IO.
- An initialized file-scope `word` is a data word placed where it is defined.
- The first parameter of a `JDA` function lives in the function's entry word, as the PDP-1 `jda` instruction leaves it.

Self-modifying code gets a real C form. A loop cursor stored in an instruction's address field is a C pointer whose storage is that instruction. Runtime code generation, such as the outline compiler that builds the ship drawing code, writes instruction words as data and then jumps to them. The dialect has no assembly blocks, and there is no interpreter.

Names in the C follow Norbert Landsteiner's "Inside Spacewar!" series. Local copies are in `source/masswerk/`. Examples are the object table, the calc routines, the outline compiler, and the Expensive Planetarium. Each definition has a comment with the original Macro symbol, so you can cross-reference the listing.

## How the project is verified

### The hash proves the binary

`pdp1cc build` compares the sha256 of the built `.rim` with the oracle. A match means every word at every address is identical: code, constants, and tables. The comparison runs at every step, so a pull request that breaks the hash cannot land. On a mismatch, the build reports:

- whether the variable block moved, which happens when the count of literal constants changes
- the first address that differs, with the expected word and the actual word
- the compiler rule that produced the wrong word

### Other checks prove the compiler reads the C

A matching hash does not prove the C means anything. A compiler could ignore its input and print stored output. These checks rule that out:

- **Reference runs.** `pdp1.h` has a second mode for `g++`. In that mode, `word` is a C++ class with exact 18-bit ones' complement arithmetic, so the lifted C runs natively. Each `tools/check-*-reference.py` runs a group of routines this way and compares them, call by call and bit for bit, with the same routines in the oracle binary in the SIMH PDP-1 simulator: the result, every word the routine may change, and the points it plots. The square root is checked over all 65,536 inputs, sin and cos over every angle, multiply and divide over edge cases plus 100,000 seeded random inputs.
- **Corpus programs.** `tests/corpus/` holds small C programs that are not Spacewar. `pdp1cc gate` compiles each one, runs it in SIMH, and compares the result with its native build. Every compiler rule must be used by at least two corpus programs that do not copy a Spacewar routine, so each rule is a general C rule and not a Spacewar special case. `tests/reject/` holds programs the compiler must refuse.
- **Hint checks.** The dialect's hints (`JDA`, `HOMED`, `SKIPNOT`, `register`, ...) are deleted one at a time, and the gate fails if the compiled output does not change. A hint that changes nothing is decoration.
- **Prediction edits.** The gate swaps operands, adds 1 to constants and to shift counts in the C, and requires the output to change in exactly the words the compiler's rules predict.
- **Lint and isolation.** `tools/check-g3.py` fails if the compiler's source contains any Spacewar symbol or any word from the oracle image. It then copies the compiler, `lift.toml`, `lift/` and the corpus into a tree without `source/` and without `build/`, compiles every file there, and runs the whole build: the hash must match. So the image comes from the C alone.
- **Frame check.** `tools/check-main-loop-frames.py` plays 17 scripted matches in SIMH on the oracle image and on the built image side by side, stopping at every frame and every halt. It reports which compiled words the game runs.

### What the checks do not prove

- **Same words, not the authors' intent.** The hash proves the image is identical. The reference runs prove that the C, read as C, computes what the binary computes for the routines they cover. Neither proves that a name or a comment is right. That part is review.
- **The main loop has no native reference.** The spaceship calc routine jumps into code that the outline compiler generates at run time, and only a PDP-1 can run that code. The spaceship check runs the routine up to that jump and from the generated code's return point, as two halves. The main loop calls the generated code too, so only the frame check and the hash cover it.
- **The frame check measures coverage, not meaning.** The two images are the same, so its comparison is clean by construction. It runs 1412 of the 1442 compiled code words. The 30 it does not run: the start vector at 3 and the sequence-break flush (6 words; no sequence break is raised), sin's overflow clamp (5), the entry of the divide routine (1; the game only calls the integer divide), the outline compiler's direction code 2 (7; no shipped outline uses it), nine words of the starfield's scan-wrap paths, an explosion path (1) and the wait loop of a ship in the star (1), both of which need a negative instruction count. `tools/check-divide-reference.py` calls the divide entry in SIMH and natively. No check measures whether the others run elsewhere; the hash covers every one of them.
- **Native hardware is a model.** The reference build models the test word, the sense switches, the display and the control boxes. Headless SIMH has no control boxes: `iot 11` leaves IO as it was, and the programs clear IO first, so both sides read no buttons pressed.

## Run the checks

You need Linux, `gcc`, `g++`, `git`, and [`uv`](https://docs.astral.sh/uv/).

1. Build the oracle:

	```sh
	tools/oracle.sh
	```

	The last line is `build/oracle.rim: OK`.

2. Build the lifted image and compare it with the oracle:

	```sh
	uv run pdp1cc build lift.toml
	```

	The last line ends with `MATCH`.

3. Build the SIMH PDP-1 simulator from an open-simh checkout:

	```sh
	git clone --depth 1 https://github.com/open-simh/simh.git /tmp/simh
	tools/build-simh.sh /tmp/simh
	```

4. Run the gate, the lint and isolation check, the unit tests, the reference checks and the frame check:

	```sh
	uv run pdp1cc gate
	uv run python tools/check-g3.py
	uv run python -m unittest discover -s tests
	for c in tools/check-*-reference.py; do uv run python "$c"; done
	uv run python tools/check-main-loop-frames.py
	```

	Each command exits with status 0. The gate ends with `gate ok`, each reference check reports `0 differ`, and the frame check reports `differences: 0`.

## Repository layout

- `source/` has the original assembly and the masswerk pages.
- `lift/` has the lifted C. `lift.toml` lists the files in tape order.
- `tools/pdp1cc/` is the compiler. `tools/pdp1cc/include/pdp1.h` defines the dialect.
- `tests/corpus/` has the non-Spacewar test programs.
- `tools/` also has the oracle build, the SIMH build, and the check scripts. `tools/macro1.c` is the assembler source.
- `ref/` has the SIMH PDP-1 CPU source, the reference for instruction semantics.
- `docs/` has the design: [grounding](docs/grounding.md), [synthesis](docs/design/synthesis.md), the three design candidates, and the [lift playbook](docs/lift-playbook.md).

## Sources and credits

- Spacewar! 3.1 (24 Sep 1962) by Steve Russell, Martin Graetz, Wayne Wiitanen, Peter Samson, Dan Edwards, and others at MIT.
- "Inside Spacewar!" by Norbert Landsteiner, [masswerk.at](https://www.masswerk.at/spacewar/inside/).
- open-simh: the SIMH PDP-1 simulator and `macro1`.
