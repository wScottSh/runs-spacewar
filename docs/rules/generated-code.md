# Rule under test: code generated from a command table

Written 2026-11-09, before reading any PDP-1 program other than Spacewar! 3.1. It states a compiler rule in PDP-1 terms, with no name from Spacewar, so that other programs can test it. It goes into `runsc` only if it fits programs other than Spacewar unchanged, with only binding data differing.

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

## What the binding may vary

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

An occurrence fits when all five hold and its differences are binding keys from the list above. An occurrence that needs any other difference shows the rule is too narrow.

## What it is not

Patching one instruction's address field (`dap`, `dip`) to step a cursor or set a return is a different idiom. The PDP-1 does it everywhere, and `runsc` already compiles it from slots and parameters. The census counts a program as generating code only when it writes several instruction words into a buffer and then jumps into that buffer.
