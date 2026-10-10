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

The lift is in progress. Each routine is lifted in its own pull request, and every merged step reproduces the original binary. `pdp1cc build` prints which source regions are compiled from C. The rest of the image still comes from the original assembly text until its region is lifted. The finish line is a build from `lift/` alone, with no original source in it.

Milestones are listed in [the lift playbook](docs/lift-playbook.md). Decisions and their evidence are logged in [`docs/decisions.tsv`](docs/decisions.tsv).

## How the lift works

1. `tools/oracle.sh` assembles the original source, `source/spacewar3.1_complete.txt`, with `macro1`, the PDP-1 Macro cross-assembler from open-simh simtools. The output, `build/oracle.rim`, is the oracle. Its sha256 is `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`.
2. `pdp1cc` compiles each lifted C file in `lift/` to PDP-1 Macro text.
3. `pdp1cc build` replaces each lifted region of the original source with the compiled text, assembles the result with the same `macro1`, and compares the sha256 with the oracle. It also leaves out the macro definitions that no unlifted line uses any more (`[[dropped]]` in `lift.toml`). They make no words, so the hash still matches.

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

- **Reference runs.** `pdp1.h` has a second mode for `g++`. In that mode, `word` is a C++ class with exact 18-bit ones' complement arithmetic, so the lifted C runs natively. Each pure math routine is run this way and compared, bit for bit, with the original binary's routine in the SIMH PDP-1 simulator. `tools/check-sqt-reference.py` covers all 65,536 inputs of the square root. Routines that draw are compared by the points they plot: SIMH reports AC and IO at each display instruction, and the native build records each point. `tools/check-heavens-reference.py` covers the central star and a full turn of the starfield.
- **Corpus programs.** `tests/corpus/` holds small C programs that are not Spacewar. `pdp1cc gate` compiles each one, runs it in SIMH, and compares the result with its native build. Every compiler rule must be used by at least two corpus programs, so each rule is a general C rule and not a Spacewar special case.
- **Lint and isolation.** `tools/check-g3.py` fails if the compiler's source contains any Spacewar symbol or any word from the oracle image. It also compiles the corpus and the lifted C in a copy of the repo without `source/` or the oracle files, and checks that the output is identical.
- **Mutation checks.** A change to an operator or a constant in the lifted C must change the output where the compiler's rules predict, and the hash must fail.
- **Hint checks.** These are planned. Each compiler hint is removed in turn, and the gate fails if the output does not change.

### What the checks do not prove

The reference runs cover the math routines, the outline compiler, the heavens, and the calc routines for explosions, torpedoes, hyperspace and a ship in the star (`tools/check-objects-reference.py`). The rest of the game logic depends on code that the outline compiler generates at run time, and only a PDP-1 can run that code. For those regions, the hash is the whole verdict. `tools/check-main-loop-frames.py` plays scripted matches in SIMH on the oracle image and on the built image side by side. Since the images are the same, it measures coverage rather than meaning: which compiled words the game runs. Because the hash covers every word, it is enough to show that the game is the same.

The checks do not judge whether the C reads well. That part is review.

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

4. Run the corpus, the lint, and the reference checks:

	```sh
	uv run pdp1cc gate
	uv run python tools/check-g3.py
	uv run python tools/check-sqt-reference.py
	```

	Each command exits with status 0.

## Repository layout

- `source/` has the original assembly and the masswerk pages.
- `lift/` has the lifted C. `lift.toml` maps each C file to the source lines it replaces.
- `tools/pdp1cc/` is the compiler. `tools/pdp1cc/include/pdp1.h` defines the dialect.
- `tests/corpus/` has the non-Spacewar test programs.
- `tools/` also has the oracle build, the SIMH build, and the check scripts. `tools/macro1.c` is the assembler source.
- `ref/` has the SIMH PDP-1 CPU source, the reference for instruction semantics.
- `docs/` has the design: [grounding](docs/grounding.md), [synthesis](docs/design/synthesis.md), the three design candidates, and the [lift playbook](docs/lift-playbook.md).

## Sources and credits

- Spacewar! 3.1 (24 Sep 1962) by Steve Russell, Martin Graetz, Wayne Wiitanen, Peter Samson, Dan Edwards, and others at MIT.
- "Inside Spacewar!" by Norbert Landsteiner, [masswerk.at](https://www.masswerk.at/spacewar/inside/).
- open-simh: the SIMH PDP-1 simulator and `macro1`.
