# Rule under test: code generated from a command table

Written 2026-11-09, before reading any PDP-1 program other than Spacewar! 3.1. It states a compiler rule in PDP-1 terms, with no name from Spacewar, so that other programs can test it. It goes into `runsc` only if it fits programs other than Spacewar unchanged, with only declaration data differing.

## The idiom

A program keeps a list of commands as data. At one stage it writes, for each command, a fixed run of instructions into a buffer. At a later stage, and usually many times, it jumps into the buffer, and the code runs straight through and jumps out to a fixed place. The buffer is the commands compiled into code: a display list built as code, or a pattern compiled before it is drawn.

## The pure RUNS it compiles from

- A Record `L`, a collection whose field holds a member of an enum `E`, the command kinds. Data only.
- A **decoder**: a Processor (or a Network of them) that writes `L`, one command after another, at a stage that fires less often than the walker.
- A **walker**: a Processor whose body walks `L` from a start slot, and for each slot matches the member and runs a straight run of statements for it. One member ends the walk.
- The walker's arms read and write only fixed fields of Records, never `L` itself.

## What the compiler emits

1. **A template per member of `E`**: the instructions that the compiler produces for that arm of the walker, by its ordinary rules, with the walk's cursor removed. The ending member's template ends with a jump to the code the Network runs after the walker.
2. **The generator**, in place of each of the decoder's writes of a member `m` to `L`: code that writes `m`'s template, word by word, at the buffer's cursor and advances the cursor.
3. **The entry**, in place of the walker: a jump into the buffer where this instance's list starts.

## What the declarations may vary

These are data, one key each, and differ from program to program:

- Where the buffer lies, and where each instance's entry is kept.
- How the generator writes a template: word by word inline, or a word that recurs through a shared subroutine, or a shared tail of words that several templates end with.
- How the decoder dispatches on a command: a jump table or a chain of tests, and where each arm lies.
- Which words of the image the generator patches in place, if any.

## What it assumes, each a test against an occurrence

1. **Fixed templates.** The generated code is a concatenation of one fixed run of words per command. If a template has holes that the generator fills from data (an operand, a count), the rule as written does not cover it.
2. **Two stages.** The code is generated at one stage and run at another, not in the same pass.
3. **Straight runs.** The generated code has no loop of its own. Its state lives in registers and in fixed words, not in the buffer.
4. **One way in, one way out.** It is entered by a jump to the start of an instance and leaves by a jump to one fixed place.
5. **A finite command set**, each member with its own template.

An occurrence fits when all five hold and its differences are declaration keys from the list above. An occurrence that needs any other difference shows the rule is too narrow.

## What it is not

Patching one instruction's address field (`dap`, `dip`) to step a cursor or set a return is a different idiom. The PDP-1 does it everywhere, and `runsc` already compiles it from slots and parameters. The census counts a program as generating code only when it writes several instruction words into a buffer and then jumps into that buffer.

## Census, 2026-11-09: the rule as written fails

The rule above was committed (f797c28) before any other program was read. The census then ran every PDP-1 program it could get.

**The corpus.**
- 265 tapes from the Computer History Museum restoration archive (`bitsavers.org/bits/DEC/pdp1/papertapeImages`), the music score tapes left out.
- Sources from the same tree (`from_peter_samson/`: `dpys5.mac`, `lives2.mac`, `pdp1m16.mac`, `hc1d.mac`, `sw41f.mac`; `ddt/raphael/`) and from masswerk.at (Spacewar 2b and 4.4).

**The lever.** `tools/census_generated_code.py TAPE` boots a tape as the machine does, attached to the reader in read-in mode, so a tape's own loader reads its blocks. It starts counting at the first instruction below the loader. It follows core through SIMH's CPU history and reports every run of words that the program writes whole and then executes. Its core model is compared with SIMH's core at the end of every run.

**Calibration.** On Spacewar 3.1, both the oracle built here and the archive's own tape, it reports one run and nothing else: `03772-05245: 684 words`, written by `oc`, leaving to `sq6`. That is the outline buffer.

**Coverage, and its limit.**
- Of 273 runs, 64 booted and reached a program.
- 198 tapes use a loader format that SIMH's read-in rejects (`Format error`).
- 218 runs executed fewer than 100 instructions, most of them programs that wait for typed input or are parts of the timesharing system.

A path that runs only on input the census did not give is not seen. The static pass below covers the sources.

**What it found.** Every hit, classified by reading the code:

| Program | Hit | Idiom |
|---|---|---|
| Spacewar 3.1, 4.1f, 4.2a (and the tape labelled `newSpacewar_4-30-60`, which is 3.1) | a 684-word buffer from `oc`, entered each frame | **the rule's idiom**; one program family |
| Minskytron (`dpys5.mac`, start 500) | `sh0`–`sh5`: at start, `gsh` takes 3 bits of the test word, picks a shift instruction from a table, and stores it; the display loop runs each with `xct`, every pass | an instruction chosen from data at one stage and run at a later one, at fixed single sites |
| Music player (`pdp1m16.mac`, static) | `lio (skp` / `(skp i` into `mps`, `dvs` by whether multiply and divide work; `(clf 2` / `(stf 2` into fixed sites by switch 5 | the same, at fixed single sites |
| Expensive Typewriter | `dio 501`: an instruction stored into the input-wait loop | the same, at a fixed single site |
| Expensive Desk Calculator | 2751, 2766 set from constants at start; 101 decremented as a whole word | fixed-site selection; the cursor idiom done with `add` |
| Macro assembler (monitor) | 112: an `add` whose address the program steps with `dac i` | the cursor idiom |
| DDT (static) | `lio (jda tr`, `dio i bk1`: a breakpoint written into the user's program | a debugger patching another program |
| `possible`, multi-segment tapes | words written by a loader in the program | loading, not generation |

**Verdict: REFUTED.** No program outside Spacewar's lineage builds a buffer of code from a command list. A compiler rule for it would be used by one program, which the standing orders forbid.

**What the census found instead.** At least four programs outside Spacewar choose an instruction from data at one stage and run it at a later stage: Minskytron, the music player, Expensive Typewriter and the Desk Calculator. Spacewar's outline compiler is the sequence form of the same thing: it chooses one instruction run per command and lays the runs one after another. That idiom is general enough to test. The next test is to state it as a rule and compile Minskytron from pure RUNS with it, to its original words.
