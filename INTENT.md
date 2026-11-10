# RUNS: the intent, as the Spacewar port found it

This is a working note from a verbatim port of Spacewar! 3.1 to RUNS. The RUNS documents point in the right direction but are wrong in many details, so this note reasons from what RUNS is for and checks each claim against the running original. It records what the port and the design discussion have settled so far.

## What RUNS is for

RUNS exists so that a game's rules outlive the machine they were written for. The source is a text that anyone can read, run, and change, and that any future runtime can rebuild into the same game.

Five requirements follow from that purpose:

1. **The game is ported exactly, warts and all.** Every sequence of inputs from power-on must give the same game. That includes every glitch play can reach, because a glitch is part of the game. A re-release of Super Mario 64 without the backwards long jump would not be Super Mario 64. A port never changes the game to fit RUNS. Where RUNS cannot yet say what the game does, RUNS grows.
2. **The text is the game.** It is deterministic and total, so every faithful runtime produces the same game. Nothing about the game may live only in a binary.
3. **Every rule can be swapped.** A rule is replaceable only if its whole contract is visible. A Processor's contract is the Records it reads and writes, and nothing else. A hidden channel, such as a register left set, a shared scratch word, or a patched instruction, would break every swap. That is why all data flows through Records.
4. **The structure is visible.** The order and the conditions under which rules fire are rules too. The Network writes them where anyone can see them and change them.
5. **Variation is native.** A house rule is an edit to one Processor or one Network line, not a fork of a program.

## The three parts

- **A Record** is anything the game remembers. Examples are the object table, the random number, the frame's time budget, and the tunables. There is no separate category for global data. A Record holds one value or a fixed-size collection.
- **A Processor** is one rule. It declares the Records it reads and the Records it writes. Inside its body it may compute freely, including updating those Records in place. Purity holds at the boundary: what the Processor does is a function of what it declares.
- **A Network** is the game's skeleton. It fires Processors and sub-Networks in order, chooses with guards, and iterates with bounds. It writes nothing. A guard only tests values that Records hold and computes nothing on them; a condition that needs arithmetic is a Processor writing a Record, which the guard tests. A `run` passes only which slot. The Network states the original's order, because the Records cannot: `collision` and the calc routines all write the object table, and their order changes 294 of 300 frames. Each value the Network moves between Processors goes through a Record.

Every Record is one of three kinds: the game's, the interface's, or the presentation's. A Processor touches the game and the interface, or the presentation and the interface, never the game and the presentation. [Game, interface, and presentation](#game-interface-and-presentation) says why.

The topology is a Petri net. Records are the places and Processors are the transitions. No value flows from one transition straight into another. An earlier draft had a fourth kind, the function, which took words and returned words. A Processor called it, so a value went from one rule to another as a call and a return, with no place in between. That broke the topology, and functions are gone. The only calls left are the word's own operators, such as `rcl`, `scr` and `popcount`. Call syntax for writers, if it comes, belongs to tools that write RUNS, not to RUNS.

A Network can state a contract the way a Processor does, with `reads:` and `writes:`. The Records it declares cross its boundary. Every other Record its Processors touch is its own. A top Network, one that nothing fires, is a whole program, and it must state its contract: what comes in from the world, and what the presentation sends out. A game may have several top Networks. Spacewar has three: the two start Networks, one of which the host fires once when the operator starts the machine, and the frame, which the host fires once each frame. Together they are the game, so a Record they share does not cross the boundary.

A field with no initial value is unknown until the game sets it or the world gives it. That is how the text says what comes in: the console's switches, and the words core held at power-on. Reading a field while it is unknown is an error. A top Network whose routines read a Record with such a field declares that Record under `reads:`.

`wait`, in a Network, hands the world the firing. The host shows what has left the game and may change what comes in, and then the firing goes on. Spacewar waits when it halts to show the scores between games: the operator may flip the test word switches before continuing, and the game reads them after the halt.

The evaluator in `tools/runs.py` enforces these rules before anything runs. A Processor's declarations are its text's, in both directions: it declares each Record its text reads (`reads:`) or writes (`writes:`, which lets it read the Record too), each once, and each Record it declares is one its text reads or writes. A `jump` may touch whatever the instructions the program builds name. A Record that the game's Processors write and nothing in the game reads leaves the game, so the top Network declares it under `writes:` (`lights`). Each expression's type is checked: a number (a word or a count), a condition, an instruction, a member of an enum, or a pair; a member where a number goes, or an instruction where a word goes, is an error of the text, not of a run. A routine that fires itself is an error. A call of anything but a word operator is an error. A Processor that fires a routine is an error. A Network with `let`, `set`, `emit` or `return` is an error, and so is a Network loop without a guarded exit. So are a `break` or `continue` outside a loop, a parameter or local the routine never reads, a number that does not fit a word, a constant slot past its collection, a compare of two constants, and an ordering compare (`<`, `<=`, `>`, `>=`) with anything but 0 on its right, unless its left is a parameter or a counted loop's variable (`requires: slot < 2`). A top Network, or a Network that states a contract, must declare each stream its Processors write and each Record they share with Processors outside it, and a top Network must declare each Record with an unknown field that it reads. A Processor that nothing fires shares nothing at run time, so it does not count: the tunables the spaceship executes wait in the text for the spaceship. While the game runs, a Processor that reads or writes a Record it did not declare is an error, and so is reading an unknown field. Code a Processor runs with `jump` goes through the same contract, word by word. In a program whose Records all have kinds, a Processor that touches a presentation Record and a game Record is an error, so is a presentation Processor that writes an interface Record, and so is a guard that reads a presentation Record over a game routine.

## Game, interface, and presentation

Games outlive their hardware only if the presentation can be removed and replaced whole, with no change to a rule. Presentation is the screen, the sound, the controls, the pacing, and the machine underneath. It can be rebuilt for each platform. The game cannot.

The separation is in the Records. Each Record is one of three kinds:

- **Game**: what only the rules use. Fuel, the random number's state, angular momentum, the collision radius.
- **Interface**: what the game and the presentation share. The game writes what there is to show, such as positions, headings, and the random numbers the drawing uses. The world writes what comes in, such as the control word, the sense switches, and the words core held at power-on.
- **Presentation**: what belongs to one platform. The pen, the compiled outlines, the planetarium's window, the frame's time budget, the scope's points.

A Processor that touches a presentation Record is the presentation's, and every other Processor is the game's. The loader enforces three rules. A presentation Processor touches no game Record. It writes no interface Record, because only the game and the world write the interface. A guard that reads a presentation Record guards only the presentation's routines. In Petri net terms, the presentation's transitions take nothing from the game's places and give nothing to them, so deleting the presentation's transitions leaves every firing of the game's the same.

The Network fires both kinds in one order, the order the game needs and the original ran. Deleting every presentation Processor and every run of one leaves the game. A new platform supplies its own presentation Processors and Records against the same interface. The Network's presentation lines are the moments the game offers a presentation. A platform fills them, leaves them empty, or edits those lines in plain view.

What decides a Record's kind is what its values reach, not what the code was written for. A value is the game's if any rule can observe it. The game touches the machine in only four ways:

1. **A value comes in**: the controls, a clock, the network, the contents of core at power-on. It is an interface field with no initial value.
2. **A value goes out** to the presentation. It is an interface field the game writes.
3. **The machine computes something the rules then read.** The PDP-1 wraps a sum around, a video chip latches a collision, a draw routine works out where a sword is. That computation is a rule of the game, and it moves inside the game. Ocarina of Time's `Player_PostLimbDrawGameplay` (`src/code/z_player_lib.c:1657` in the decomp) computes Link's body part positions and his sword's collider quads from the draw matrices, so part of its drawing is gameplay.
4. **Timing**: how long a frame takes, which thread ran first. Where the game's state depends on it, it becomes a rule (Spacewar's `cycles` estimates are one: they set how long an explosion lasts) or a value that comes in.

Only the third could widen the interface, and it is always resolved by moving the computation into the game. So the interface grows in data, such as a longer list of points, but never in kinds of thing.

Spacewar's original code mixes the two in single routines (read in the C lift, `lift/`). Each mix is a split to make:

- The central star is presentation, but it draws two random numbers each frame (`run next_random` in `central_star` and `star_line`, `runs/heavens.runs`) from the generator that also decides hyperspace jumps and whether a ship survives breaking out (`lift/objects.c:117`, `:126`, `:167`). Sense switch 6, which turns the star off, changes hyperspace. The two draws are the game's; the line drawn from them is the presentation's, and it reads the numbers from the interface.
- The explosion's dots draw two random numbers each (`lift/objects.c:55-56`). The draws are the game's; the dots are the presentation's.
- The exhaust flame draws a random number of dots, and each dot burns a unit of fuel (`lift/spaceship.c:232`, `:243`). In the original one loop does both, and the RUNS still does: `exhaust` writes fuel and plots dots. The loop moves up into the Network, with the fuel burn the game's and the dot the presentation's.
- The ship outlines and the Expensive Planetarium are presentation. The planetarium draws no random numbers (`runs/heavens.runs`).
- The spaceship draws its outline by walking strokes. At each new game the outline compiler decodes each ship's outline into strokes in `outline_code` (a step, a store or restore of the pen, an end), which the declarations lay out as code in the free core after the object table. Each frame the spaceship sets the `pen` and walks its strokes (`draw_outline`), leaving the pen at the ship's tail, where the exhaust flame starts (then `run after_outline(slot)` in `runs/spaceship.runs`). The walk's other effects are the points, the position it stores and restores (`pen.saved_x`, `pen.saved_y`), and `pen.side`, program flag 5, which it sets before it reads it and which nothing in the game reads (the planetarium clears flag 5 before it reads it, `oracle.lst` 570). Compiler, strokes, walk and pen are all presentation. Just before the jump the spaceship plots a dot at the center at intensity 0. On the PDP-1 that dot asks the display for the completion pulse the outline's first point waits for.
- The torpedo's start was computed through the pen: `stx = sx1 - ssn`, where `sx1` is where the outline starts. It was the one place the spaceship's rules read a presentation word, as the deleted copy below shows. Split: `aim_nose` (the game's) computes the ship's nose and the torpedo's start from it, and `aim_outline` (the presentation's) starts the pen at the nose. The declarations keep the nose in the pen's words (`[share]` in `pdp1/spaceship.toml`), so the image does not change. Checked (before the strokes): a copy of the game with the outline, the pen, the exhaust's dots, the outline compiler, `outline_code` and `type insn` deleted matches SIMH on every game Record over 1,000 spaceship calls, and a planted fuel defect is caught.
- The spare-time loop is pacing. `begin_frame` sets the frame's budget, `charge_time` and `spare_time` alone use it, and nothing in the game reads it after (`runs/frame.runs-prim`; inferred from the ported slice, not yet from the whole game).

An earlier version of this note kept presentation code where the original runs it and only said which of its effects the game must keep. That left Processors that write both fuel and the display, so no platform could replace the presentation without touching a rule. The kinds replace it. The loader enforces the rules on a program whose Records all have kinds. Until every Record of `runs/` has one, `tools/check_purity.py` lists what is still impure, and the conversion is done when it reports 0.

### Spacewar's boundary so far

The three top Networks of `runs/frame.runs` declare what crosses between the program and the world. When the Records have kinds, `console`, `score` and `controls` are interface Records the world writes, and `display` is the presentation's.

- **What comes in.** `console`: the test word switches, the control boxes, and the six sense switches (1, 2, 3, 5 and 6 the spaceship's; 4, which turns the planetarium off, the heavens'; 6 the central star's too), each a field named for what it does when on. `score`: the two scores and the games left in the match, whose starting values are what core held at power-on. Which start Network the host fires is the operator's start address, 4 or 5. Each of these is a field with no initial value. `controls`: which device the control word comes from, the operator's choice of start address, made before the first frame. `outline_code`: the outlines' strokes. The tape does not load them, so they have no initial value, and the start's new game decodes them before the first frame; the frame declares them as it declares `controls`.
- **What goes out.** `display`, the points the scope plots. `scoreboard`, the scores the halt between games shows on the console lights. `lights`, program flags 1 and 2, which light for the ship that survived a game and which nothing in the game reads.

The control word is the spaceship's input. The start Network sets `controls.source`, and each spaceship fires the `control_word` Network once a frame, which reads the test word or the control boxes from it.

## Exactness, glitches, and the machine

A glitch is one of three kinds, by what it reads.

1. **A logic glitch** is the game's own logic, such as the backwards long jump. A verbatim port keeps it with no extra work. Spacewar has one: the previous control word is never stored, so with sense switch 3 on the fire button always counts as newly pressed (`lift/spaceship.c`, the torpedo code). The port keeps it (`trigger` in `runs/spaceship.runs-prim`).
2. **A layout glitch** reads past an array, through a stale pointer, or one kind of object as another: DOOM's `spechit` overflow, Ocarina of Time's stale reference manipulation. In those states the rule is whatever lies next in memory, so the layout is part of the game. Where play reads the layout, the RUNS text states it.
3. **A machine glitch** runs data as code, or jumps into the middle of a routine: arbitrary code execution. On that path the rule is that the machine runs those bytes. Exactness means the original machine's instruction semantics are part of the game, used only where play reaches them, and the original code bytes are part of the game's data.

These share one piece: a description of the original machine. It already supplies RUNS's types (the PDP-1's 18-bit ones' complement word). Where play reads the layout, it supplies the layout. Where play runs into machine behavior, it supplies the instruction semantics. The rest of the game is RUNS.

The declarations to a target machine holds only the choices play cannot observe. Where the game states a layout, the declarations follow it.

A halt or a hang the original reaches is a rule, not an error. Spacewar halts when a ship fires and the object table is full (the `hlt` loop after the search for a free slot, `stop` in `launch_torpedo`). A loop bound or a `requires` that fails in the evaluator means the port is wrong, never that the game may do anything. A `requires:` is a precondition, as a loop's bound is: it states which firings the port is for (`slot < 2`: a ship's slot), it compiles to nothing, and deleting it changes no firing it lets run. It is not game logic, so no declaration or image can catch its deletion. The evaluator checks it at every firing of every check against SIMH, and `tools/check_compiled.py` shows each one stops some firing and leaves every other the same.

A loop's bound (`loop at most N`) and a jump's (`jump ... at most N`) are the same kind of thing: RUNS's check on the port, not a proof about the game. Each compiles to nothing. The evaluator stops a firing that runs past one, and every check against SIMH would then fail. The gate passes a changed bound when every firing it makes either stays the same or stops at a bound. No tool shows that a committed bound is tight, or that it holds on a sequence of play the SIMH checks do not reach. Only `sine_reduce`'s 2 is shown to hold for every input: all 2^18 words run. The bounds are:

| Routine | Bound | What it counts |
|---|---|---|
| `explosion` | `0400001` | the dots, until `explosion_cloud.particles` counts up to 0 (`mz1`) |
| `spare_time` | `0400001` | the spare-time loop, until the frame's budget counts up to 0 |
| `spaceship_in_star` | `0400001` | the wait in the star, until `pen.down_x` counts up to 0 |
| `launch_torpedo` | `030` | the search for a free slot (`sr1`), past which it stops |
| `compile_outline` | `0140` | the outline's codes (`och`) |
| `square_root` | `023` | the passes, until `square_root_call.passes_left` counts up to 0 |
| `sine_reduce` | `2` | the passes that reduce the angle (every word checked) |
| `draw_star` | `2` | the line's two halves |
| `show_magnitude` | `(past - first) >> 1` | the stars of one magnitude, each looked at once at most (`fin`) |
| `head_out` | `3` | the passes that bring the new heading within a turn |
| `exhaust` | `040` | the flame's dots (`sq7`) |
| `draw_outline` | `0304` | the strokes of one outline, each at most once a side |

Which Records need a layout stated, and where play runs into the machine, is a fact about play, not a guess. `tools/reach_oracle.py` measures it.

## Where play reaches the machine in Spacewar

`tools/reach_oracle.py` runs the oracle image in SIMH through the lift's seventeen scripted matches (real play from the start address, every sense switch setting, the full object table), 9,649 stops and 59 million instructions. It names every data access by the Record field or label it lands in, and lists each site where play depends on the PDP-1 rather than on a stated rule. It checks itself: its copy of core matches SIMH's at the end of every scenario, and its model of every add, subtract, shift and rotate (5.97 million of them) matches the AC SIMH shows after each. The full report is `docs/reach-oracle.txt`.

| What it finds | Where | What it means for the port |
|---|---|---|
| One instruction reads several places | 31 sites. The outline compiler and the compiled outlines; the planetarium's star display; `clear mtb, nnn-1`; `mot`. | The first two are presentation. `clear` zeroes every table in one loop over contiguous core, and play sees only the zeros. `mot, lac .` (source line 865) reads `not+slot` for every colliding object, so for torpedoes it reads past the 2-word outline array into `nco`, `nh1` .. `nh4` and the first words of `outline_code`. The value goes to `sp5`, the spaceship's jump into its compiled outline, which only the spaceship calc routine uses, and slots 0 and 1 set it right before. Play never observes it. Only the spaceship jumps through `sp5`, and only `ss1` and `ss2` run it, which only slots 0 and 1 ever hold: a ship's routine word comes from `place_ships` or back from `ships.saved_routine`, and never carries the sign bit, so the walk reads `not+slot` for the ship's own slot just before its calc routine runs. Checked: `tools/check_frame.py poison` patches SIMH's main loop so that every slot past the ships loads a jump to address 0 into `sp5`, and 1,500 frames with flying ships, torpedoes and collisions still match the evaluator, whose spaceship draws `ships.outline[slot]` and never reads past the array; poisoning the ships' slots too stops SIMH at once. So the read past the array is the declarations' (`carry` in `pdp1/main_loop.toml`), and the RUNS text does not state it. The word the declarations carry is the one the RUNS walk starts from (`let at = ships.outline[slot]`): `runsc` takes the field from the walk, and refuses the carry unless every calc that reaches the walk runs after the walk that loads it, in the same slot, and nothing in between writes the field. A house rule that keeps a ship out of the collision walk is refused by name, not built into a different game. |
| Reads of core the tape never loaded | `1sc`, `2sc`, `gct`, `moc`, `mas` | The scores and the game count start from whatever core held at power-on. The scores are cleared only after a match's scores are shown (source lines 784-785), and the first match's tie test (`lac 1sc; sas 2sc`, lines 768-769) and game count (`lac gct`, line 764) read them. So their starting values come in at the boundary: `score` has no initial value, and the start Networks declare it. `moc` (`frame.objects_seen`) and `mas` are counted and never read. |
| Code the program writes, then runs | `outline_code` (684 words); `mi1` | Outlines are presentation, and the port runs them as the original does: the RUNS compiler writes instruction values into `outline_code`, and `draw_outline` runs them by the machine's rules (below). `mi1` is the explosion's `scl`, built from a random number; the port states it as a rule (`popcount`) and the checks match it. |
| Code read as data | `mot`'s reads into `outline_code` | The same `mot` read as above. |
| Jumps to unnamed places | none, other than returns from a call | |
| Halts | `sr1+6` (line 1250), the full object table | A rule: `stop` in `launch_torpedo`. `tools/check_spaceship.py` and `tools/check_frame.py` reach it, and the evaluator stops where SIMH halts. |
| The word's machine behavior | 730 sites | All of it is the `word` type's semantics, which RUNS already states. Positions wrap around the screen in the inertia (`diff`, lines 1000-1003, 1178-1186), hyperspace jumps (1022-1025) and the explosion's dots (973-975), and the collision test's distance wraps (`mx2, sub .`, line 871, 23,520 times): the screen is a torus because the word wraps. The random generator wraps by design. Shifts of negative numbers round toward zero, and some tests see minus zero. A compiler for another machine must give the `word` these semantics. |

No layout read that play observes has turned up, `mot`'s included. The power-on words are the one place Spacewar's play reaches the machine outside the `word` type.

The head of the tape also holds words that belong to the machine and its operator, not to the game. Each was weighed by what play can observe:

- **The sequence break words (0-3) and the flush (`sbf`).** Play never raises a sequence break: the tape never executes `esm` (no `720055` in `oracle.lst`), so a break can happen only on a machine another program left in sequence break mode before the game ran. The lift's frame check runs none of these words. They are layout, and the flush is the PDP-1 back end's runtime text in `runsc`.
- **The start vectors at 4 and 5, and the control word routine slot at 040.** Starting at 4 or 5 chooses whether the control word comes from the control boxes or the test word switches, and the slot is where an operator builds a private control word routine. The two starts also differ in play: 5 goes to `a`, which reads the game count and the scores core held at power-on, and 4 goes to `a6`, which sets the game count from the test word first. (An earlier note here said they differ only in the control word's device; the listing says otherwise, lines 756-762.) So the start address is an input: the host fires `start_with_test_word` or `start_with_control_boxes`. Which address fires which is the console's, presentation like the sense switches and the lights, and `pdp1/devices.toml` states all of them in one place. The vectors that jump there, and the slot, are layout.
- **The tunables' fixed low addresses.** They sit there so an operator can change them from the console between games. In RUNS that change is an edit to a Processor or a field, a house rule, so the addresses are layout. The values are rules: the instructions are Processors in `tunables.runs-prim`, the numbers are fields of the `tunables` Record.

The PDP-1 declarations lay all of them out (`pdp1/tunables.toml`), and `runsc` emits the machine's words as the PDP-1 back end, the way it emits `jda`.

## How the original's routines map

The original passes values between routines in AC and IO, and that is what had made functions look natural. Each of its three ways of sharing a rule now becomes Processors and places.

- **A subroutine** (`jda sqt`) is a Processor over the routine's own words. `jda` leaves the argument in the entry word `sqt`, and the routine leaves the root in `sq2`, so `square_root` reads `square_root_call.entry` and writes `square_root_call.root`. The scratch words `sq1` and `sq2` are fields of the same Record, because they are the routine's places in the original too.
- **A tunable executed with `xct`** (`the`, `hd2`, `hd3`, `hr1`, `hr2`, `tlf`) is a Processor of its own. What it takes from AC and IO and what it leaves there are fields of the `handoff` Record. A routine that executed one becomes a Network: a Processor sets the input, the tunable fires, and a Processor uses the output. An operator can still patch the rule and not only the number.
- **A subroutine that calls another** (`imp` calls `mpy`) is a Network. A Processor sets the callee's Record, as the caller's AC and the word after its call would, the callee runs, and a Processor reads the callee's results. The word after a call (`jda mpy / lac b`) is the callee's argument by name: the callee executes it each time it reads it. No caller in Spacewar names a word the callee writes, so it is a field the caller sets once (checked against every call site in the listing).
- **A skip return** (`dvd` and `idv` return one word further when the quotient fits) is a result the caller reads, so it is a Record field: an enum, `division`, whose members are the two outcomes. The declarations say which member skips.
- **Two entries into one body** (`idv` shifts its dividend and jumps into `dvd`) are a Network that runs the first Processor, then the shared routine. That the second is entered by a jump past its entry word is the declarations'.
- **A loop with two entries.** `sin` enters its reduction loop at `si1` (add 2 pi) when the angle is negative and one word later when it is not, and the loop's last jump goes back to `si1`. Structured text cannot enter a loop in two places, so the RUNS states `if a < 0: a = a + 2 pi` before the loop and ends the loop's body with the same statement. The declarations lay the two out as one (`loops = "exit first"`); the image is the original's.
- **A macro** (`random`, `diff`) is a Processor too. `random` updates `random.number` in place. `diff` reads its acceleration from `handoff.acceleration` and moves one axis of one object, so it is two Processors, `inertia_x` and `inertia_y`. It leaves the new position in AC, and the torpedo takes it up from there, so the position goes out through `handoff.position`. A loop that runs a macro moves up into the Network. The explosion's dot loop is the case in this slice.
- **A register a later rule reads without setting.** The explosion clears IO once (`cma cli`) and its dots shift each new random number in on top of the last dot's y; hyperspace shifts its draw in on top of whatever the main loop left in IO. Each IO is a `handoff` field the rule reads, as the original reads the register. The shifts push the old value all the way out, so it never reaches a Record or a point.

`handoff` holds only values that the original carried in a register from one rule to the next. Each field names the register and the instruction in a comment. A value that a Processor computes and uses itself stays a local. A word that the original keeps in core between two rules is a Record field named for what it means, such as `explosion_cloud.particles` (`mxc`).

Splitting a routine at each macro or tunable leaves its skips in the Network. Each guard tests what the original's skip tests. `count i ma1, tc1` becomes `run count_down(slot)` followed by `if objects.counter[slot] >= 0:`.

The main loop and the game control add four shapes:

- **A label that several places jump to** (`a`, `a4`, `a5`, `a6`, `a2`, `ml1`) is a Network of its own, and each jump is a `run` of it as the last thing a branch does. The declarations lay each one out as a block, and pdp1cc drops a jump to the block that follows.
- **The main loop's own jump back to `ml0`** is the end of a firing: the host fires the frame again. The declarations name the frame as the Network the PDP-1 repeats.
- **A halt that waits for the operator** is an `emit` of what it shows, then `wait`.
- **The cursors' walk** is `for slot in 0 .. 026`, and the comparison loop inside it is `for other in slot + 1 .. 027`. Which cursor points at which field, which instruction holds it, and how the walk steps them are the declarations'.

The spaceship adds six:

- **A program flag that one routine sets and tests across its calls** (flag 6, the rocket fires) is a Record field, `spaceship.rocket`, an enum. The declarations hold it in the flag.
- **A jump into code the program generated, which jumps back** (`sp5`, the compiled outline) is a walker, `draw_outline`, over the strokes that code holds, and then a run of the Network the code jumps back to. That the walk is a jump through `sp5` into code is the declarations'.
- **A label several branches of one routine jump to** (`bsg`) is a Network that each branch runs as its last thing. The compiler lays it out once, where the last branch runs it.
- **The search for a free slot** is a Network loop over a field that holds a slot, `launch.slot`, that ends in `stop` when the table is full. The declarations keep the field in the search's cursor and builds the new torpedo's cursors from it.
- **A store of an address part** (`dap`) keeps the rest of the word: `set objects.cycles[launch.slot] = objects.cycles[launch.slot] & 0770000 | 020`.
- **A scratch word reused for a second meaning**: the ship in the star counts its wait in `\ssn`, the outline's first step. The RUNS text uses the same field, `pen.down_x`, as the original does. Nothing reads it before the next ship sets it.

The outline compiler adds the shapes of code that writes code:

- **Code the program writes, then runs** is a collection of commands and a walker over it: `outline_code.stroke`, an enum, which the compiler writes one stroke a direction code, and `draw_outline`, which walks a ship's strokes each frame, an if-chain arm a member. The declarations hold the collection as code (`held_as_code`, the run form of `docs/rules/held-as-code.md`): each slot's words are its member's arm, which `runsc` compiles as a `TEMPLATE` and `pdp1cc` compiles to words with its ordinary selector, and the slots lie end to end; a write of a slot stores its member's words (`LAY_OUT`), and the walk is a jump into them. The text holds no instruction. Checked: `tools/check_outline_compiler.py` spells the evaluator's strokes as those words and compares them with SIMH's `oc`, word for word.
- **A jump inside the code to a place the compiler chose** (the end's jump back to the nose, `ocm`) is a field that holds a slot, `outline_code.back`, which the walker jumps to (`set at = outline_code.back[at]; continue`), copied from `outline_compiler.start_over`, set where the nose is written. The declarations hold both as code (`held_as_code`): the jump to that slot, `dap ocm`, then `ocm` copied whole.
- **A position in the code** is a word that holds a place in a collection (`outline_call.code`, `ships.outline`). The declarations keep it as the address of the slot's words (`[into]`); the RUNS text never says where the code lies. Checked: `tools/check_spaceship.py moved` has SIMH's compiler lay the outlines out from 05000 instead of right after the table, and every call still matches.
- **How the compiler lays a stroke's words out** (`ocs` laying out the swap twice from IO, `comtab` and `oce` sharing a step's last words, `ocd` laying out every arm's last word once, `ocn` built for the end's jump past the return) is the declarations' layout, which the text does not state: a store routine (`[[place]] store`, `times`, `loaded`), pdp1cc's cross-jumping (`tails = "shared"`), and the routine's jump word.
- **A dispatch on a number** (`dispatch`, a jump through a table on the direction code) is an if-chain over 0 to 7. The code for 7 ends the outline; its arm writes the end and breaks out of the loop. A Network loop's exit is an `if` with an arm that ends in `break`; the arm may run things first.
- **A loop with two entries** (`ocj` reads the next outline word and falls into `och`, which reads the next code) is one loop over codes that reads the next word at its end. The statements before the loop and at the end of its last `if` are the same; `runsc` lays them out once.
- **The outlines themselves** are data on the tape: a Record whose field gives each slot its own initial value, one line a slot. In RUNS they are part of the text; conceptually they are an asset (AEMS).

The heavens add four:

- **A macro with arguments laid out once a run, with words of its own** (`dislis J, Q, B`, once a magnitude) is a Processor with parameters, `show_magnitude(m, first, past, intensity)`, run four times with constants. What each copy keeps of its own (the homes of `star_x` and `star_y`, the scan's start `fpo`, the cursor `flo`) is the declarations': the locals are each copy's, and the cursor is the slot `m` of `magnitudes.cursor`.
- **A value held in an instruction and compared as one** (`fyn, lio .`, then `idx fyn / sad (lio Q+2`; `fpo, lio`, then `sad fpo`) is a place in the catalog, a local word in RUNS: `star_y == past`, `star_y == scan_start`. That the comparison is of `lio` words is the declarations'.
- **A jump into a run of copies** (`bjm, jmp .` into `bds`, 16 dots, past as many as a random number says) is a counted loop from a local, `for dot in skipped .. 017`. The declarations lay it out as the jump (Duff's device).
- **A program flag a routine clears, then sets and tests** (flag 5, a star was plotted; flag 6, the line's mirrored half) is a local of an enum (`scan`, `half`): each routine clears it before it reads it, and nothing reads it after. The declarations hold it in the flag.

The star catalog is data on the tape: a Record, `star_catalog`, whose one field takes a value a slot, written as the source writes each star (`8192 - 1537`, `371 << 8`, from `mark 1537, 371`). Conceptually it is an asset (AEMS). Where it lies (`6077/`) is layout: nothing but the planetarium names it, and it reads the catalog through its own places. It lies right after the free core the outlines' code takes, 02105 words (`[code_words]` in `pdp1/main_loop.toml`), which `runsc` reserves after the object table; the catalog follows them, so another size builds another image. The compiler writes 0132 strokes, 684 words.

## What the port showed

**The 1962 program is already shaped like RUNS.** The object table is a Record collection. Each calc routine is a Processor. The routine word in each slot names the rule that runs the object, which makes it a state. The main loop's jump through that word is a guarded dispatch on that state. The tunables that the original keeps as instructions to execute (`the`, `hd2`, `hr1`, and others) are the authors' own swap points.

**The Network holds gameplay, not plumbing.** The main loop decides who collides with whom and when. Object *i* is tested against every later colliding object and can explode both. Then *i*'s calc routine runs, in the same frame, on the changed state, before *i+1* is touched. The last slot is never tested and never counted. These are rules of the game. Moving the collision test into its own phase after all objects move, as an earlier conversion did, changes 294 of 300 test frames (`tools/check_frame.py` on a variant of `frame.runs`).

**Firing is sequential, and each write is seen at once.** A Network runs its Processors in declared order, and each one sees everything earlier ones wrote. That is how a Petri net fires, one transition at a time. Concurrency is a property a compiler may derive from the declared reads and writes. It is not part of the model, and assuming it would change Spacewar.

**The machine falls away where play does not reach it.** Each PDP-1 device in the original maps to a RUNS form:

| In the original | In RUNS |
|---|---|
| Cursors kept in instruction address fields | The Network's slot index |
| `jsp` and `jda` calls, `xct` of a tunable, a macro | `run` a Processor or a sub-Network |
| Values in AC and IO | Locals inside a Processor; between Processors, a field of `handoff` |
| A routine's own scratch words (`sq1`, `mxc`) when they pass between Processors | Record fields |
| The routine word's address plus its sign bit | An enum, and a guard that compares it with `explosion` and `in_hyperspace` |
| The scores and game count core held at power-on | Fields with no initial value, declared by the top Networks |
| `hlt`, showing the scores, then reading the switches again | `emit scoreboard`, then `wait` |
| Code the program writes and then runs | a collection of commands (data) and a walker over it; the declarations hold the collection as code |
| A shift instruction built at run time and executed | A shift by a counted number of places |
| IO left over from the main loop in `in_hyperspace` | `handoff.jump_low`, which the draw shifts out (checked: SIMH runs each call with a random IO) |

The cursors are layout the program uses but play never observes; `tools/reach_oracle.py` counts 54 of them.

**Exactness is about the game, and placement is about the machine.** The port keeps every word that carries meaning from one routine to another or from one frame to the next. That includes `objects_seen`, which is counted and never read, as a Record that no Processor reads. The graph shows that it is dead. A value that one Processor sets before it reads it and never hands on becomes a local, such as the dot's coordinates in `plot_particle`. Machine-only words such as `mas`, a cursor that is stepped and never read, drop out. To rebuild the exact binary, a compiler needs a second artifact, the PDP-1 declarations (`pdp1/`, which `tools/runsc.py` compiles with the RUNS text). The declarations place Records in core, spells enum values as words, and lays out the scratch. It holds only what play cannot observe.

## The draft language

The syntax is a working draft. These are the forms this slice needed:

- `record name[N]` with typed fields and initial values, and `stream` for ordered output (the display's points). A field with no initial value comes in from outside the game (the scores at power-on, the console).
- `enum`, and `match` over an enum in a Network. The evaluator checks that every member has an arm.
- In bodies: `let`, `set` (which updates a local or a declared Record field), `if`, `elif`, `else`, `loop at most N:` with `break`, `continue`, and `return` (which carries no value), `for i in a .. b` (a counted loop: `mpy`'s 17 multiply steps), and `emit`.
- `let (high, low) = scl(h, l, 3)` names the two halves a pair operator returns. A half the rule drops is `_`, which nothing may read (`sine_answer`).
- The word's operators: `ral`, `rar`, `popcount`, and the AC:IO pair operators `rcl`, `rcr`, `scl`, `scr`, `mus` (multiply step) and `dis` (divide step), which return the pair: `set (high, low) = mus(high, low, m)`.
- In Networks: `run`, `if`, `for i in a .. b` (bounded and ascending, and the bounds may depend on an outer index), `match`, `stop`, `unreachable`, `wait`, `requires:`, and the contract, `reads:` and `writes:`. A guard is any expression that writes nothing; `breakout`'s `if (random.number | 0400000) + ships.uncertainty[slot] >= 0:` is one.
- The Network loop, `loop at most N:`. Its body fires and chooses like any Network body, and it must hold an `if <guard>: break` among its own statements. The guard reads Records that the Processors in the body write. The loop runs its body, in order, until a guard breaks. Running past N passes means the port is wrong, as it does in a Processor. The explosion's dot loop is the form:

  ```
  loop at most 0400001:                                     # mz1
    run next_random
    run scatter_particle
    run next_random
    run plot_particle(slot)
    if explosion_cloud.particles >= 0:                      # count \mxc, mz1
      break
  ```
- Two enums may share a member's name (`off` and `on` of `light` and `switch`). A member's name means the member of the enum it is compared with or stored as, in the evaluator and in `runsc`, which spells it by that enum's declaration. The spaceship needed this: the sense switches and the lights are both off or on.
- `stop` in a Network: the machine halts, and halts again each time it is continued. The full object table is the case.
- `type insn` in the machine description: `instructions:` lists the PDP-1 instructions the game reaches, and `display:` the stream `dpy` plots on. An instruction is built by its name: `lac(pen.x)`, `jmp(outline_code.insn[k])`, `jmp(after_outline)`, `stf(5)`, `rcl(9)` (with one operand, the instruction; with three, the pair operator), and `cma`, `ioh`, `dpy` with none. A field of type `insn` holds one.
- `jump <word of code> at most N`, in a Processor: run the code from that word by the machine's rules, at most N instructions, until it jumps to a routine, which the Network runs next.
- A field of a collection whose line ends in `=` takes one initial value a slot, one line each, under it (`outlines.codes`).
- A Network loop's exit is an `if` with an arm that ends in `break`. The outline compiler's end runs its last words, then breaks.
- `word` is the PDP-1's 18-bit ones' complement word. Add and subtract are the machine's. A word compares with 0 by its sign, and `==` compares all 18 bits.

Totality comes from the bound on each loop, not from forbidding `break`.

## Decisions that other games force

A swarm stress-tested this draft against Super Mario Bros., DOOM, Ocarina of Time, Journey and an Unreal Engine game (the analysts worked from memory of those games; their claims are not checked). Where it stands:

| Question | Where it stands |
|---|---|
| What comes into the game | The top Network's contract declares it. |
| Arithmetic in guards | Allowed; a guard writes nothing. |
| Call syntax | Not in RUNS; tools may offer it. |
| Layout | Stated in the text where play reads it; the declarations hold the rest. |
| Crashes and hangs the original reaches | Rules. |
| Objects made and freed at run time, and references to them | The game's own allocator is ported. A stale reference does what the stated layout says. |
| Recursion | A stack Record and a bounded Network loop; a stack that overflows is layout. |
| Floating point | Types of the original machine, as `word` is. Library math is code, ported as Processors. |
| Assets | AEMS, a separate protocol. |
| Versions | Each version is its own game. |
| Code with no source | Ported from its machine code. |
| Running data as code | Commands as data and a walker in the text; the declarations hold the commands as the walker's code (`held_as_code`). Spacewar's compiled outlines are the case. The evaluator still parses `type insn` and `jump`, which no program here uses. |

## Verified

`tools/check_all.sh` runs every check in the first list on each change, in about ten minutes on 32 cores; the counts are its own. The checks against SIMH run the RUNS source in the evaluator and SIMH running the oracle image on the same Records. The second list was run by hand, with larger counts.

What `check_all.sh` runs:

- The image. `tools/runsc.py` compiles the RUNS text and `pdp1/` to the original tape image (sha256 `8744e9c9...`), and refuses RUNS the evaluator rejects, a program's declarations key it does not know, a member, field or routine the RUNS text does not have, a read of a shared word that holds another name, and a `carry` the RUNS jump does not agree with (`pdp1/README.md`, "What a program's declarations may not say").
- The declarations hold no game logic (`tools/check_compiled.py --sample 8000`: a seeded sample of the full gate below). Of the 8,000: 3,663 change the image, 2,832 are refused by `runsc`, 1,412 are rejected by the evaluator, 90 are shown the same game, 2 deleted `requires:` and 1 loop bound pass as RUNS's own checks; none is silent, dead or a crash.
- `square_root`: all 65,536 inputs match the observed vectors (`tools/check_square_root.py`). This one is not against SIMH.
- `multiply` and the Network `integer_multiply`: 101,453 calls each, all match on AC, IO, `mpy`, `mp2` and `imp` (`tools/check_multiply.py`, against SIMH: every pair of 38 edge values, the nine observed pairs, and 100,000 seeded pairs).
- `divide` and the Network `integer_divide`: 107,224 and 107,227 calls, all match on AC, IO, `dvd`, `idv` and the skip (`tools/check_divide.py`, against SIMH: every pair of 38 edge values with five low halves, the observed inputs, and 100,000 seeded triples; 53,875 and 382 of them overflow).
- The Networks `sine` and `cosine`: 20,046 words each (20,000 seeded and the edges), all match on AC, `sin`, `cos`, `mpy` and `mp2` (`tools/check_sincos.py 20000`, against SIMH and the observed vectors). Two passes of the reduction loop reduce every word, so its bound is 2.
- The twelve tunables the original executes with `xct`, as Processors over `handoff`: each against SIMH executing its word, the scalers of AC over every word, the constants over 1,000 AC:IO pairs, `hr1` and `hr2` over 101,444 pairs (`tools/check_tunables.py`). The eight tunables kept as numbers, and `random.number`'s initial 0, are the oracle image's words.
- The Networks `explosion`, `torpedo`, `in_hyperspace`, `breakout`: 1,000 calls each, all match (`tools/check_calc_routines.py 1000`).
- The outline compiler, against SIMH's `oc` word for word (`tools/check_outline_compiler.py`): the needle, the wedge and seven synthetic outlines (every code in every position of a word, the 7 code first, in the middle and last in a word, after a store and after a restore) all match on every word laid out, where the code ends, the compiler's own words and flag 6; and a new game with `separate_outlines` at -0, +0 and four other words of either sign matches on where each ship's outline starts and every word of the code space.
- The spaceship calc routine, the Networks `first_spaceship` and `second_spaceship`, run whole through the outline, which the evaluator walks as strokes: 1,000 calls, all match on the object table, the ship properties, the random number, the spaceship's own words, the pen, the arithmetic routines' words in core, flag 6, the search's cursor, where it halts, and every point (`tools/check_spaceship.py 1000`); 300 more with SIMH's outlines laid out from 05000 (`moved`).
- The heavens (`tools/check_heavens.py 1000`): the central star, 1,000 calls, all match on the random number, `bx`, `by`, the jump into the line (`bjm`), flag 6 and every point; the Expensive Planetarium, 4,000 frames in a row and 1,000 from set counters, margins and cursors, all match on the counters, the margin, each magnitude's cursor, the scan's start, the homes of `star_x` and `star_y`, flag 5 and every point. Every statement of the heavens' Processors runs.
- The frame Network, one whole frame from `ml0` to its jump back: 300 frames, and the same 300 with SIMH's main loop poisoned to load a jump to address 0 into `sp5` for every slot past the ships (`tools/check_frame.py 300`, `300 poison`). It compares every word of `objects`, `ships`, `random`, `frame`, `tunables`, `spaceship`, `pen`, `planetarium` and `magnitudes` where the declarations place them; `bx` and `by` with whichever of the star and the ship wrote them last; flag 6 as the rocket when the star did not draw, else that the star left it set; the search's cursor (`launch.slot`); whether it halts on a full table; and every point. It does not compare `handoff` (registers), the arithmetic routines' own words, `explosion_cloud`, the outline compiler's words, flag 5, the lights or the scores: no frame's restart delay runs out, and `tools/check_game.py` covers scoring.
- The game control (`tools/check_game.py 3000 3000`): the start Networks from power-on, the restart checks, scoring, the match count, the halt between games and the new game, which runs the RUNS outline compiler. 3,000 seeded cases against SIMH, all match, with 1,226 starts from power-on (random scores and game count in core), 1,009 halts whose second test word is given at the `wait`, and 2,199 new games. Also the lift's seventeen scripted matches, 3,000 stops each: at each frame the evaluator fires the frame from SIMH's Records; the 71 games that end match through the halt (38 shown) and the new game, and every other frame's restart delay matches. A field the evaluator does not know while SIMH does is a difference, except the lights, which keep what the machine held at power-on and nothing reads. The `control_word` Network matches mg2 and cwr on 2,000 calls with random IO and test word.
- The contracts are checked when the program loads: without `writes: display` the frame does not load, and without `reads: score` neither does `start_with_test_word`. So are the names each routine uses (`runs.check`).

Run by hand at 6e9bb2d, the full gate (`tools/check_compiled.py`, 13 minutes on 32 cores): 40,445 mutants of the RUNS of every routine the declarations compile, of every field's initial value and of every program's declarations. RUNS, by kind: numbers 375, initial values 2,027, field references to a field of the same type 5,265, of another type 939, of another Record 324, operators 276, members 90, run targets 13,919, run arguments 489, negated guards 105, if/else and arm swaps 19, match arm swaps 22, deletions 669, duplicates 836, adjacent swaps 521, moves 2,978, inserted statements 2,380, sets made locals 166, `reads:`/`writes:` entries deleted 289, `requires:` deleted 7. Declarations: key lines and sections deleted 407, list and table elements deleted 152, values replaced 8,188. 18,506 change the image; 14,300 are refused by `runsc` with a BindError that names the construct; 7,212 are rejected by the evaluator before anything runs (every `reads:`/`writes:` deletion, every field reference of another type); 406 build the original image and are shown the same game (403 by firing the mutated routine, or a bound routine that compiles it, before and after on 200 seeded Record states and up to 60 Records as play leaves them, all alike, at least 50 clean through the mutated routine; 3 initial values the declarations keep in a flag or a skip, `outline_compiler.six`, `divide_call.outcome` and `spaceship.rocket`, by 60 games of 30 frames from power-on that put out the same at every firing and end the same); 7 `requires:` deletions pass as preconditions (each stops some firing and leaves every other the same); 14 loop-bound mutants pass as bounds (every firing the same or stopped at a bound). None is silent, no declaration key, element or value is dead, and none crashes `runsc`. Reviewer D's harnesses, re-run at 6e9bb2d: 10,433 expression replacements, 22,895 structural mutants and 52,158 type substitutions with no crash; every mutant that builds the image and plays differently (44, 45, and 51 untested by play) is a mutant of a loop or jump bound, and the gate's bound judge passes each of the 89 it fires; the 404 mutants the earlier gate showed the same, fired again 1,500 times each, are all the same; every match arm that passes another argument than the slot is refused. Still silent there, and not game logic: the order of an enum's members (the declarations spell each member) and the 7 `requires:`.

Run by hand, `sine` and `cosine` at 3f917aa and the rest at e86268f (the evaluator, the RUNS text, `tools/pdp1.py` and these checks are the same at both commits and since):

- The Networks `sine` and `cosine` on every one of the 2^18 input words each: all match SIMH and the observed vectors, and no word reaches the series' saturation at +-1 (`lac (377777`): the overshoot test never passes. The port keeps the branch verbatim; only the image gate covers its code.
- The spaceship, 3,000 calls, all match, 168,609 points; the calls cover rotation with and without sense switch 1, thrust (658) and fuel burned (636), gravity (596), the star's capture both ways (441 thrown to the corner, 440 exploded), hyperspace entry (251), torpedo launch (185) and a full table (10 halts). The same 3,000 match with SIMH's outlines laid out from 05000.
- `explosion`, `torpedo`, `in_hyperspace`, `breakout`: 3,000 calls each, all match, 6.1 million points.
- The central star, 3,000 calls (68,564 points); the Expensive Planetarium, 12,000 frames in a row and 3,000 from set words, all match.
- The frame, 1,500 frames, all match, with 4,747 collisions that hit, 2,009,045 points and four halts on a full table; the same 1,500 match with `sp5` poisoned past the ships; with the ships' slots poisoned too (`poison-all`, 50 frames), SIMH stops.

Run by hand when each unit was ported, not since: `tools/reach_oracle.py`, which checks its own copy of core and its model of the word's arithmetic against SIMH (above); and the mutation runs through `tools/mutate.sh`, each caught by the checks: in the frame, skipping adjacent collision tests, testing objects that do not collide, skipping slot 0, an off-by-one in the time charge, a wrong torpedo explosion counter, and dropping the second `random` from the explosion's dot loop; ten mutations of the outline compiler; fourteen of the game control; seventeen of the spaceship (two the same game: testing `1 == fuel` for `0 == fuel`, and passing 0 for the IO the second divide takes); twenty-three of the heavens; and five wrong rules of the machine in the evaluator (`sub` adding, `rcl` one place short, `szf` never skipping, `dpy` plotting y for x, `dio` storing AC).

## Not yet ported

Nothing. Every unit of `lift.toml` comes from RUNS.

`tools/runsc.py` compiles the arithmetic subroutines (`sqt`, `mpy`, `imp`, `dvd`, `idv`, `sin`, `cos`), the head of the tape (the tunables, with the machine's words around them), the calc routines for explosions, torpedoes and hyperspace (`mex`, `tcr`, `hp1`, `hp3`, with the `random` and `diff` macros laid out at each use) the main loop with its game control (`ml0` to `jmp ml0`, `a1` to `mg4`) the spaceship calc routine (`ss1` to `po1`), the outline compiler (`ocs`, `oc`), the outlines (`ot1`, `ot2`), the core layout after the code (the constants, the pool words, the patch space and the object table), the heavens (`blp`, `bpt`, `bck`) and the star catalog from RUNS and their declarations (`pdp1/`) to the exact tape image. The C it writes stands alone: `build/runs/lift` holds only the thirteen generated files, and no file of `lift/` takes part in the build (checked by tracing every file the build opens). The main loop needed two additions to the language: fields with no initial value, which come in, and `wait`. The spaceship needed one: enums that share a member's name. The outline compiler needed three: `type insn` and its instructions, `jump`, and initial values a slot; and one rule eased, a Network loop's exit that runs things before it breaks. The heavens needed no addition to the language.
