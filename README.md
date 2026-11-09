# Spacewar! 3.1 in RUNS

Spacewar! 3.1 (MIT, 1962) written in RUNS, verbatim: the exact game over every sequence of inputs from power-on, glitches included. RUNS is specified in [runs-spec](https://github.com/enduring-game-standard/runs-spec).

`INTENT.md` says what RUNS is for and what this port settled. `docs/decisions.tsv` logs each decision with its evidence. `docs/adr/` holds the architecture decisions, including the earlier verification method's; ADR-0017 says which still hold. `CONTEXT.md` is the glossary.

## Layout

- `runs/` is the game. Records and Networks are in `*.runs`, Processors in `*.runs-prim`.
- `pdp1/` is the PDP-1 binding: how the PDP-1 carries the RUNS text. It holds only choices that play cannot observe. `pdp1/README.md` states the contract.
- `tools/runs.py` is the reference evaluator. It parses RUNS, checks it, and runs it.
- `tools/runsc.py` compiles the RUNS text and the binding back to the original tape image, byte for byte. It emits the lift's C dialect, and `tools/pdp1cc` compiles that.
- `tools/check_*.py` compare each RUNS routine, run by the evaluator, with the original running in the SIMH PDP-1 simulator.
- `tools/check_compiled.py` changes the RUNS text and the binding one edit at a time. Each edit must change the image, be refused, or be shown to leave the game the same.
- `lift/` is the C lift: Spacewar hand-lifted into a C dialect that `tools/pdp1cc` compiles to the original image. RUNS now generates every unit of it, so `lift/` is the reference the checks and notes cite. `docs/c-lift/README.md` describes it, and `tools/check-*-reference.py`, `tests/` and `ref/` are its checks.
- `oracle/` holds input and output vectors recorded from the original, which some checks read. `source/` is the original listing and Norbert Landsteiner's "Inside Spacewar!" notes.

## Run the checks

You need Linux, `gcc`, `g++`, `git`, and [`uv`](https://docs.astral.sh/uv/). Build the oracle, the image from the C lift, and the SIMH PDP-1 simulator once. Some checks read the lift's build listing.

```sh
tools/oracle.sh
uv run pdp1cc build lift.toml
git clone --depth 1 https://github.com/open-simh/simh.git /tmp/simh
tools/build-simh.sh /tmp/simh
```

Then run the port's checks:

```sh
tools/check_all.sh
```

It prints `MATCH` when the image compiled from RUNS has the original's sha256, `8744e9c9c8540cc5075c5cbb91c56745a4305fdf8e7afca43bea2e9e04ca4bdf`, and then one line for each check.

The C lift has its own checks: the compiler's gate, its unit tests and the reference checks. `docs/c-lift/README.md` says how to run them.
