# The PDP-1 binding

`tools/runsc.py` compiles the RUNS text in `runs/` to the original Spacewar! 3.1 tape image. Each file here binds one unit of `lift.toml`: it says how the PDP-1 carries the RUNS routines and fields of that unit. `runsc` emits the lift's C dialect from the RUNS text and the binding, and `tools/pdp1cc` compiles that to the image. Every unit has a binding: the generated C stands alone, and no file of `lift/` takes part in the build (`build/runs/lift` holds only the thirteen generated files).

## What a binding may say

A binding holds only choices that play cannot observe:

- **Tape order.** `[[place]]` entries in the order their words lie on the tape: a routine, or a list of Record fields.
- **Calling convention.** How a routine is entered and left: `JDA`, `JSP`, `BLOCK`, `XCT`, laid out in place, a skip return.
- **Storage.** Which register or word carries a value: an AC or IO local, a JDA entry word, a pool word, the address field of an instruction (a cursor), the word after a call (by name).
- **Layout of code.** Where a block of a routine's code lies when the original lays it out of order.
- **Devices.** Which console instruction or sense switch holds each input field, which program flag lights for each output field, and at which address the operator starts each top Network. This is the presentation side of the boundary: play sees the input's value and the output's value, never the device, and a binding for another machine maps the same fields to its own controls and lights. All of it is in one file, `pdp1/devices.toml`, which `runsc` and the checks (`tools/pdp1.py`) both read; no other file names a switch, a light or a start address.

## The vocabulary

A `[[place]]` with `fields` lays out those Record fields as data words, with their RUNS initial values. A `[[place]]` with `routine` compiles a Processor or a Network to one C function:

- `convention`: `JDA`, `JSP`, `XCT`, as the lift's dialect spells it (`tools/pdp1cc/include/pdp1.h`). An `[[inline]]` entry takes the same keys and binds a macro: the routine is laid out at each run, as a `static inline` function of each unit that runs it, whichever binding binds it.
- `entry`: the field that is the JDA entry word, where the call leaves AC.
- `ac_param`: the field that arrives in AC, for a routine with no entry word (`XCT`).
- `byname`: the field that is the word after the call, executed each time it is read.
- `result`: the fields that hold the result when the routine returns: AC, then IO.
- `io_param`: the field that arrives in IO.
- `io`: locals and fields that live in IO. The rest live in AC or in a word of their own. A local set from a value already in IO is that value, with no move.
- `cells`: other fields that live in the routine's entry word.
- `skips`: a field and a member: the routine returns one word further when the field holds the member.
- `block`: the routine's body is a block that other routines of the unit jump into. The routine's own entry stores its entry word and jumps there too. A run of the routine as the last thing another routine of the unit does is that jump: the jumper stores the entry word, as jda would have.
- `block_takes_entry`: the block is entered with the entry word already in AC (`sin` loads it; `cos` jumps in past the load).
- `shifts = "xct"`: each shift of the routine is executed from a constant word (`xct (sar 3s`), as the `diff` macro runs the shift it is passed.
- `pool`: locals that live in a pool word (`\hpt`), not in AC.
- `loops = "exit first"`: each loop of the routine is laid out with its first exit falling through into the code after the loop, and the rest of its body after the routine's last return, jumping back to the top. When the loop's body ends with the statement that an `if` just before the loop runs, that statement is the loop's top, and the loop is entered there or one statement past it. It changes the order of the code, not what runs.
- `convention = "BLOCK"` on a Network: a block that others jump to. A `run` of it is a jump, and it must be the last thing its branch does.
- `inline`: the field that is the constant word after the call (`jda oc / ot1`).
- `io_reads`: fields a guard of the routine reads into IO, because AC holds a value the routine still needs (`lio ddd`, `lio i \mfu`). IO has only a sign test (`spi`), so it applies to a guard that tests the sign, of a field or of a field at a slot.
- `spill`: AC locals kept in a pool word from their last set on, and read from there (`dac \mt1`).
- `result` with the field in `io`, for `JSP`: the routine returns in IO (`io_word`).

A `[[code]]` entry binds a Processor whose body is a `jump` into code a Record holds (`draw_outline`). It has no code of its own: the Record's words are its code. Its run is a jump to them, and the run the RUNS text makes right after it is where the code jumps back, so that run compiles to nothing. It is a calling convention.

- `pulse = true`: the code waits for the display's completion pulse before its first point and leaves its last point's pending. So the point the RUNS text plots just before the run asks for a pulse (`dpy-4000`, at intensity 0), and the routine the code jumps back to waits for it first (`ioh`). It is the display's handshake, which play cannot observe.

A code entry a walk carries (`carry`) is reached through its home: its run is a jump through the homed word (`sp5, jmp .`), and the unit that runs it holds the home.

A Network bound as one routine runs its Processors inline, under its guards and loops. A `run` of another bound routine is a call: the sets of that routine's parameter fields just before the run are its arguments, and a parameter field that lives in a register is passed in it. A two-word result is read from the returned AC:IO pair. A one-word result is in AC when the call returns, so the statement right after the run takes it from there, as `xct hd2 / dac i ma1` does; when that statement does not read it, the call stands alone.

The keys that hold for a whole unit:

- `registers`: Records whose fields live in AC or IO, never in a word of their own (`handoff`). A field there is a local of the routine that uses it.
- `pool`: fields that live in a pool word (`\mxc`).
- `[cursors]`: a field to the cursor on the current object's slot. In a routine whose parameter is the slot the main loop's cursors point at, `objects.x[slot]` is `*x_slot`. `pdp1/main_loop.toml`, the unit that holds the walk, binds them all; every unit uses them.
- `[homes]`: fields held in a shift instruction. `"table"`: a pointer in the address field of the `xct` that runs one shift of a table (`msh, xct .`); the table's entries are the counts the RUNS text sets the field to, in text order, and a `[[place]]` with `shifts` lays the table out. Setting the field to the next entry steps the pointer (`idx msh`), to the first sets it (`law mst / dap msh`). `"built"`: the shift instruction itself, built at run time from `popcount(w & m)` and run where it stands (`mi1`). The shift is the pair operator that takes the field as its count; the pair it shifts is one AC:IO local.
- `[spell.<enum>]`: the word each member is: a number, or a routine's address, with the sign bit when `sign` is set (the object does not collide).
- `[streams]`: the instruction that takes a stream's values, its first in AC and its second in IO: `dpy` plots a point; `hlt` shows the two on the console lights, and must be followed by the Network's `wait`, which the halt is.
- `[spell.<enum>]` may also spell a member of an enum held in a program flag as 0 or 1.
- `pdp1/devices.toml`, `[console]`: a field read by an instruction of the console (`lat`, `control_boxes`), not from core. `or_into_io`: the device ors into IO, so IO is cleared first. `{ sense = n }`: a field the console's sense switch n holds (`szs`), an enum spelled 0 and 1. `[lights]`: a field held in a program flag that lights on the console. `[[start]]`: a start address (`at`) and the top Network the operator's start there fires; `tape = true` on the tape's own start.
- `[flags]`: a field held in a program flag; setting it to the member spelled 1 is `stf`, to the one spelled 0 `clf`.
- `pointers`: fields that hold addresses, which the C dialect types as `word *`.
- `[addresses]`: a field that always holds an address the layout fixes. `"after table"`: from the first word after the table, for the field's count of words.
- `[table]`: Records laid out field after field, each field's slots together, from one array (`at`); `clear` names the cursor of the loop that clears the whole table.
- `[walk]`: the cursors' walk over the table's slots. The cursors are set after the Processor `set_after`, each from the table's start in the table's order. `index` is the field whose cursor steps last and ends the walk. `homes` and `home_in` say which instruction holds a cursor homed in this unit: the first one of the unit that reads or writes the field, or the first one in the named Processor. `[walk.other]` gives the cursors of a walk from the slot after another's. `carry` names `[[code]]` routines whose jump the walk loads into its home as that walk begins. The word is the one the RUNS jump goes through: the jump's index must be a field at the routine's slot (`jump outline_code.insn[ships.outline[slot]]`) that holds a place in the code (`[into]`) and has a cursor. `runsc` refuses the carry unless every calc that reaches the jump runs after that walk in the same slot, under guards that hold for its routine word, and nothing the slot runs writes the field. So a house rule that keeps a ship out of the collision walk is a BindError that names the jump and the guard, not a different game. `stray` is a cursor no field has, stepped after the named field.
- `repeat`: the Network the PDP-1 runs again when a firing ends, as the host does.
- `[[place]] exit = "<name>"`: the shared exit of the unit's JSP routines (`srt, jmp .`), laid out where it stands. Every block of the unit that runs off its end jumps there, and it returns to the caller of the JSP routine that entered the blocks. It replaces `repeat` for the unit.
- `[cursors."<field>"]`: the cursors on the slot a field holds, not on a routine's own slot (`launch.slot`: the free slot a new torpedo takes). Each is homed in the first instruction of the unit that uses it. Setting the field to 0 sets the first cursor to the table's start (`init sr1, mtb`). The rest are set in the table's order, each from the one before (`law nob / add sr1 / dap ss3`, then `add (nob / dap ss4`).
- `[spell.<enum>]` with `literal = true` on a routine member: its word is taken from a constant (`lac (tcr`) where the others are built by `law`. The two are the same word; which the original wrote is an encoding.
- `[walk] homes` also serves a unit that holds no walk: the cursors the main loop steps whose homes are in this unit's instructions (`mom`, `mth`, `mco`).
- `moves = "swap"`: a value moves from AC to IO by the `swap` macro.
- `[into]`: a field that holds a place in a collection (`outline_call.code`, a slot of `outline_code`) holds that place's address. The C dialect types it as a pointer. A number set into it is the address of that slot; reading the collection at the field is reading through it, and stepping the field steps the pointer (`idx`). It is storage.
- `[homes]` with `"pointer"`: an `[into]` field held in the address field of the first instruction that reads through it (`ocg, lio .`).
- `[addresses]` with a collection's field: the collection lies at an address the layout fixes, not at a place of its own. `"after table"`: from the first word after the object table (`outline_code`, nnn). `runsc` reserves the collection's RUNS count of words there, so the units after it lie past them: the star catalog lies at `6077/` because `outline_code` has 02105 slots, and a different count builds a different image.
- `[[place]]` with `slots`, `range` and `reserve`: the slots `range` of a collection's field laid out as data words with their RUNS initial values, then `reserve` words of room no rule reads (the five spare words after each outline, for an operator to make it longer).
- `[share]`: a field that lives in another field's word (`central_star.slope_x` in `spaceship.gravity_x`'s, `\bx`). `runsc` refuses it unless, in every firing of a top Network and on every path, each field is set before it is read with no write of the other between (the shared words check, below).
- `data`: fields laid out as data words inside the routine's code, at its first point control cannot reach (`ocm`, `ocn` after `oc`'s return).
- `args_done`: the Processor after which the routine steps its return address past the words after its call (`idx ocx`). Where it does so is a choice of code layout; pdp1cc needs AC dead there.
- `pulse = true` on a routine: its points ask the display for a completion pulse (`dpy-4000`, at intensity 0). Each point waits for the one before it (`ioh`), and a routine that runs it waits for its last after the run. It is the display's handshake (`bpt`, the central star's line).
- `flags`: locals held in a program flag (`{ half = 6 }`), an enum spelled 0 and 1. Setting one is `stf` or `clf`; a guard on it is `flag(n)`.
- `homes`: locals held in the address field of the instruction that reads through them (`{ star_x = "pointer" }`, `fin, lac .`). The instruction is the one the first read takes it into: IO for a point's y (`lio`), AC otherwise. On the tape the address is 0, as the source writes such an instruction with no operand.
- `into`: locals that hold a place in a collection (`{ star_x = "star_catalog.words" }`). A place by number set into one is that slot's address. Two places compared, one held by a homed local, are compared as its home instruction (`I_LIO(p)`; `I_LIO(++p)` when the step just before is the comparison's).
- `data` may name locals and a collection's field. Each copy of the Processor that holds them (a Processor laid out at each run, `show_magnitude`) gets its own: its homed locals, its data locals, and the slots of the field it names by number, laid out at the copy's end. A data local is spelled as the home instruction it is compared with, at address 0 on the tape (`fpo, lio`).
- `arms = "apart"`: in the routine's loops, the first arm of each if with an else lies apart, after the loop, and jumps back to the code after the if (to the loop's top when the if ends the loop's body); an arm that is only a break is the jump itself. The loop's breaks are one jump out, laid out at the first break in the text, which the others jump to. Data words of the copy follow (`dislis`: `fgr`, `fuu`, `flp` after `jmp fin`; `fx`).
- `exit_after`: the routine's exit lies right after the named Processor, in the skip of the guard that follows it (`isp bcc / bcx, jmp .`). Each if with no else that ends the routine, or ends such an if's arm, is laid out as a guard: its test, negated, leaves the routine, and its arm follows in line. The returns after the exit jump to it.

`runsc` lays code out by rules of its own, from the shape of the RUNS text, the same for every binding:

- A loop whose one exit is its last statement, `if c: break`, tests at the bottom and jumps back to the top while `c` fails (`count \mxc, mz1`).
- `set x = x + 1` followed by a test of `x` against 0 is one index-and-skip (`isp`).
- When an `if`'s else arm ends in an `if` whose arm ends with the statements of the first arm, those statements are laid out once, at the end of the inner arm, and the first arm jumps to them (`count i ma1, hp6`).
- `set a = -a` on an AC local followed by `set f = 0` on a place in IO is one instruction, `cma cli`.
- A guard joined with `and` and `or` is laid out as jumps: each test jumps to the arm it decides, and the last falls into the first arm. A sign test that jumps on its failure keeps its own skip with the i bit flipped (`spa i`).
- A guard on one enum field whose members' words decide it by sign and zero is a test of the word: `!= m` for every member spelled 0 is `!= 0`, for every member spelled with the sign bit `>= 0`, for both `> 0`. The guard reads the field into a local; when the arm's next guard on the field or jump through it comes first, AC keeps it, else it moves to IO.
- `field == m` for a member spelled as an address is the member's word xor the field. Two guards in a row on one comparison share the xor.
- Two sets in a row of one value, not a name or a number, load it once, when the value does not read the place the first set writes.
- `let v = ...rar(e, n)...` with `e` not a local takes `e` into `v` first: pdp1cc rotates a local in place.
- A `match` whose arms each run the routine their member is spelled as is a jump through the field's word (`lac i ml1 / dap .+1 / jsp .`).
- A Processor that sets every field of the table to its zero word in every slot is the clearing loop over the whole table.
- When an arm ends in a jump, what follows the if is its else, laid out after it.
- A Processor that returns, run inside a walk or before other routines, returns by a jump to its end.
- A `match` on a field in a pool word is a call through it (`jsp i \cwg`); the routines its members name return one result, in IO. A member spelled as a JSP slot runs the routine the slot jumps to.
- Setting a program flag, then a new AC local to 0, is one instruction (`clf 6 cla`). Two zeros plotted are cleared by one (`cla cli`).
- `set v = ral(v, n)` on an IO local rotates IO in place (`ril`).
- A guard on a field held in a sense switch or a program flag is the machine's test of it: `sense(n)`, `flag(n)`.
- A register field set from a half of a call's pair result is that half, with no move.
- An unbound Network that a routine runs as the last thing of several branches is laid out once, where the last of them runs it, and the others jump to it (`jmp bsg`).
- `stop` is a halt that halts again when continued (`hlt / jmp .-1`).
- A loop that steps a field holding a slot, then stops when it reaches a slot by number, is a search: one index of the first cursor and a test of its home instruction against the one past the last slot (`index sr1, (lac mtb nob, sr1`).
- In the slot a field holds, a store of a plain value goes through IO while AC builds the cursors' chain; any statement that wants AC first finishes the chain. `set f = f & 0770000 | n` with n an address is a store of the address part (`dap`).
- A pool field is declared by each unit that names it; they are one word. One that holds a member of an enum whose members are all spelled as routines holds a routine's address, and is declared a pointer to the routines' type, which the enum names (`controls.source`: `typedef io_word control_source(void) JSP`).
- A cursor the unit's code names and does not hold itself is declared as another unit holds it: homed in an instruction (`extern HOMED`), else a pool word. The object table is declared where another unit lays it out.
- An instruction is the dialect's constructor of its word: `lac(pen.x)` is `I_LAC(&pen_x)`, `jmp(after_outline)` is `I_JMP(after_outline)`, `dpy` is `I_DPY_NOWAIT` (`dpy-4000`). These are the PDP-1 back end's encodings, as `jda` is.
- `set c[p] = v` then `set p = p + 1`, with p an `[into]` field of c, is one store through the pointer and a step (`*p++ = v`: `dac i oc / idx oc`).
- Setting a data word that holds a jump (its initial value is one) to `jmp(c[p + k])` stores only the address (`f.addr = p + k`, `dap`).
- An if-chain with no else whose guards test one value for `== n`, or an `or` of such tests, over 0 to some n, is a jump table (`switch`, `add (T / dap J / J, jmp .`). The arm of n lies in the table and must end in a jump; the other arms lie apart. The first lies right after the table and falls into the code after the chain; the rest lie after the routine's code, each jumping back to that code. A Network that the arms run last is laid out in the first arm, and the others jump to it (`jmp oce`). A jump after an arm's last if/else goes into both of its branches. The arms share their locals, which are declared at the routine's top.
- A loop whose body ends with `if c: X`, no else, is laid out with the test at the bottom: back to the top while c fails, then X. When X ends with the statements just before the loop, they are laid out once and X jumps back to them, the loop's second entry (`jmp ocj`, then `och`). A break of a loop that is the routine's last statement is its return.
- An entry word of another unit's routine is, to the caller, AC: a value carried into the call and out of it (`jda oc`).
- A counted loop from a local up to n, that does not read its index, is a jump into a run of n + 1 copies of its body past as many as the local says (Duff's device, `bjm, jmp .` into `bds`). The jump's address is set right after the local's last set before the loop, and `runsc` refuses a local set anywhere else.
- A program flag set, then a new AC local and a new IO local set to 0, is one instruction (`cla cli clf 6`).
- A plain loop that ends the routine leaves it through its breaks: each is a return.
- An initial value may be an expression of numbers (`8192 - 1537`, `371 << 8`); the word is its value.
- A place just past a collection's last slot has an address too (`lio Q+2`).

A `[[place]]` may instead lay out words that the PDP-1 and its operator need and that no game rule reads. `runsc` knows each kind as the PDP-1 back end, the way it knows `jda`:

- `machine = "sequence break"`: words 0-2, where a sequence break saves AC, PC and IO (not punched), and word 3, a jump to the flush. `machine = "sequence break flush"`: the flush, which resumes the interrupted program. Play never raises a sequence break (`docs/c-lift/README.md`: the frame check never runs these words).
- `machine = "start vectors"`: a jump to each top Network at its start address, from `pdp1/devices.toml`.
- `jsp_slot`: a JSP routine the operator may rewrite in place, laid out `at` an address. By default it jumps to `jump` and returns what that returns (`returns`: `ac` or `io`); `reserve` words of room follow it.
- `machine = "constants"` and `machine = "variables"`: where the assembler lays out its literal constants and its pool words. `machine = "patch space"`: `reserve` words of room for the operator's patches (`p, . 200/`). No rule reads any of them as a place: a constant is a number of the RUNS text, and a pool word is a field.
- `table = true`: the object table's words, from `[table] at`. The tape does not load them and a new game clears them before anything reads them, so `runsc` requires each table field's RUNS initial value to be its zero word.

A field with no data word of its own (an entry word, a register) has no value on the tape, so its RUNS initial value must be 0; `runsc` refuses any other.

## Names

A C function is named after its RUNS routine, and a field's word `record_field`. Two fields that share a word (`[share]`) take the name of the one they share. A copy's own locals and slots take the copy's number or the slot's (`star_x_1`, `magnitudes_cursor_0`). The names do not reach the image.

## What a binding may not say

No game logic. A binding has no expressions, no statements and no number that the game computes with. Every word of the image that the game's rules decide comes from the RUNS text, and every RUNS reference is compiled as the field it names.

`runsc` enforces the parts of this it can decide before it writes C:

- It compiles only RUNS the evaluator accepts: `runs.check` (what each kind may say, the contracts, a static scope check of names, fields and runs, each Processor's `reads:` and `writes:` against its text in both directions, the type of each expression, and no routine that fires itself).
- Every key of a binding is one it knows, with a value of its kind, and every value names a field, routine, member or local of the RUNS text. A key the RUNS needs and no binding gives is a BindError. A name a binding gives a C word of its own (a cursor, the table, a block, an exit, a slot) names nothing else: no other such word, no routine, Record or field, and no word of C or of the dialect's header. A `[share]` lives in a word of its own, the table's Records are collections, a cursor is homed in one unit, the walk's index has a cursor in each walk, and a console field is read by an instruction or held in a sense switch. A member's name means the member of the enum of the field it is stored in or compared with, as in the evaluator.
- Shared words. Several RUNS names can live in one word: an entry word and its `cells`, a `[share]`, and names `runsc` compiles to one C name (a local kept in the register a field arrived in, the halves of a pair, a call's result). `runsc` follows, through every routine and across the runs between them, which names each such word holds: the last one written and those copied from it since. A top Network starts with none, and a routine's register parameter holds its field only where every run of it sets it just before. A read of a name its word does not hold is a BindError, and so is a routine that returns a result field whose word holds another name, or leaves such a word holding only its locals, unless a bit-level pass proves the Processor's effects use no bit of the value read (`draw_jump` and `plot_particle` shift IO's old value out).
- `carry` goes through the field the RUNS jump names, and only where the walk loads it for every slot that jumps (`[walk]` above). A skip return is set on every path, the skip member last.

`tools/check_compiled.py` checks the rest by mutation, in every routine and field a binding compiles. It changes each number and initial value, each field reference to every other field of its Record (of its type and of another) and to the field of its name in another Record, each operator and enum member, and each run to every other routine of its kind and arity. It negates each guard, swaps an if's arm with its else and its first two arms, and swaps each two arms of a match. It deletes, duplicates and swaps each statement with the next, and moves it to every other place in its block. After each let and set it inserts a set of each other place the routine sets, to the same value, and a step of its own place (`set p = p + 1`), and inserts that step before it too. It makes each top-level set of a field a local of the field's name, and deletes each Record of each `reads:` and `writes:` and each `requires:`. In each binding it deletes each key line, each section and each element of a list or inline table, and replaces each value: a quoted name by every other of its shape in the file, a number one up and one down, a flag flipped. A binding mutant must change the image or be refused, so no key, element or value is dead; one that builds the image passes only when the value was a name the binding gives a C word, which never reaches the image. A RUNS mutant must change the image, be refused with a BindError or rejected by the evaluator, or be shown the same game: the evaluator fires the mutated routine, and failing that each bound routine that compiles it, on 200 seeded Record states (a quarter of the words drawn from the edges: 0, -0, +-1, the extremes) and on up to 60 Record states as play leaves them before its firings (60 games the evaluator plays from the tape's words with random power-on words, console switches and control boxes), and the mutant passes only if every firing leaves the same Records, points and errors, with at least 50 running clean through the mutated routine. A loop's bound is RUNS's own check and compiles to nothing: a mutant of it passes when every firing is the same or stops at the bound it states. A `requires:` deleted passes when every firing it lets run is the same and it stops some firing.

Where play observes the layout, the RUNS text states the layout, and the binding follows it (`INTENT.md`, "Exactness, glitches, and the machine").

## Checks for a ported unit

A unit counts as ported when all of these pass:

1. `uv run python tools/runsc.py` prints `MATCH`.
2. `uv run python tools/check_compiled.py` passes.
3. Each RUNS routine of the unit matches SIMH running the original, through the evaluator, over every input or a seeded random sample with the edge cases (`tools/check_*.py`).
4. The checks of earlier units still pass (`tools/check_all.sh`).
