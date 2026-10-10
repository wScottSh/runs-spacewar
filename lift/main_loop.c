/* The main loop and the game control around it (source lines 664-941 and
 * 1357-1366): one pass of the main loop is one frame. It points the
 * cursors at the first object, checks whether the game has ended, then
 * walks the object table: it tests each colliding object against every
 * later one, calls each object's calc routine, draws the heavens and the
 * central star, and burns the rest of the frame in the spare-time loop.
 *
 * Between games it keeps the scores and runs a match of several games,
 * set on the test word switches; a new game clears the object table, puts
 * the two spaceships at their start and compiles their outlines.
 *
 * The object table sits after the code, the literal constants, the pool
 * words and the patch space: parallel arrays, one per property, stacked one
 * upon the other in one block (Inside Spacewar! part 3). The first NOB
 * slots of each array are the objects; the spaceship-only properties have
 * a slot per ship. */

#include "object_table.h"

#define NOB 030                     /* nob: objects in the table, two ships then torpedoes */
#define SHIPS 2
#define TABLE_WORDS (7 * NOB + 10 * SHIPS)

/* Each property's array, where it starts in the object table (nx1, ny1,
 * na1, nb1, ndx, ndy, nom, nth, nfu, ntr, not, nco, nh1 .. nh4). */
#define ROUTINES (object_table)
#define X_POSITIONS (ROUTINES + NOB)
#define Y_POSITIONS (X_POSITIONS + NOB)
#define COUNTERS (Y_POSITIONS + NOB)
#define CYCLES (COUNTERS + NOB)
#define DX_VELOCITIES (CYCLES + NOB)
#define DY_VELOCITIES (DX_VELOCITIES + NOB)
#define SPINS (DY_VELOCITIES + NOB)
#define ANGLES (SPINS + SHIPS)
#define FUEL (ANGLES + SHIPS)
#define TORPEDOES (FUEL + SHIPS)
#define OUTLINES (TORPEDOES + SHIPS)
#define OLD_CONTROLS (OUTLINES + SHIPS)
#define SAVED_ROUTINES (OLD_CONTROLS + SHIPS)
#define JUMPS_LEFT (SAVED_ROUTINES + SHIPS)
#define RECHARGES (JUMPS_LEFT + SHIPS)
#define UNCERTAINTIES (RECHARGES + SHIPS)
#define COMPILED_OUTLINES (UNCERTAINTIES + SHIPS)  /* nnn: free core after the table,
                                                      where the outline compiler writes */

/* The control word routine: it leaves the control word in IO, ship 1's
 * buttons in the high four bits and ship 2's in the low four. */
typedef io_word control_word_reader(register word io) JSP;
typedef void calc_routine(void) JSP;
typedef void compiled_outline(void) BLOCK;

/* Routines the main loop calls, defined elsewhere. */
JSP SYM("ss1") void first_spaceship(void);
JSP SYM("ss2") void second_spaceship(void);
JSP SYM("mex") void explosion(void);
JSP SYM("bck") void expensive_planetarium(void);
JSP SYM("blp") void central_star(void);
JDA SYM("oc") word *outline_compiler(word *code, INLINE const word *outline);
extern word needle_outline[8] SYM("ot1");
extern word wedge_outline[8] SYM("ot2");
JSP SYM("cwr") io_word control_word_routine(register word io);

XCT SYM("tno") word torpedo_supply(void);
XCT SYM("tlf") word torpedo_life(void);
XCT SYM("mhs") word hyperspace_shots(void);
extern word fuel_supply SYM("foo");
extern word collision_radius SYM("me1");
extern word collision_radius_half SYM("me2");
extern word separate_outlines SYM("ddd");

HOMED word *outline_slot;           /* mot: a ship's compiled outline, the code that draws it */
extern HOMED compiled_outline *draw_outline SYM("sp5");  /* the spaceship calc routine's jump into it */

POOL control_word_reader *control_word_getter SYM("cwg");
POOL word spare_time;               /* mtc: the frame's instruction budget, counting up */
POOL word restart_delay;            /* ntd: frames until the next game, counting up */
POOL word first_score;              /* 1sc */
POOL word second_score;             /* 2sc */
POOL word games_left;               /* gct: games left in the match, counting up; 0: no match */
POOL word objects_seen;             /* moc: counted, never read (Inside Spacewar! part 3) */
POOL word distance_x;               /* mt1: |dx| between the two objects compared */
POOL word *stray_cursor;            /* mas: advanced with the others, never set or read */

/* The other object's cursors, for the collision test: the slots of each
 * object after the current one (ml2, mx2, my2, ma2, mb2). */
HOMED word *other_routine_slot;
HOMED word *other_x_slot;
HOMED word *other_y_slot;
HOMED word *other_counter_slot;
HOMED word *other_cycles_slot;

HOMED word *clearing = 0;           /* the slot a new game clears next (the `clear` macro) */

BLOCK void objects(void);
BLOCK SYM("a1") void start_with_test_word(void);
BLOCK SYM("a40") void start_with_control_boxes(void);
BLOCK void between_games(void);
BLOCK void new_match(void);
BLOCK void new_game(void);
JSP SYM("mg1") io_word read_control_boxes(register word io);
JSP io_word read_test_word(register word io);

/* ------------------------------------------------------- the frame seam */

/* ml0: each frame starts here, with a fresh instruction budget and every
 * cursor on the first object. Then the restart checks: while both ships
 * fly on their own calc routines and one still has torpedoes, the restart
 * delay is held at twice a torpedo's life (md1). Once either ship's routine
 * is not its own (it exploded, or is in hyperspace) or both are out of
 * torpedoes, the delay counts down, and then the survivors score (mdn). */
BLOCK void next_frame(void)
{
    register word budget = -04000;
    spare_time = budget;

    word *slot = ROUTINES;
    routine_slot = slot;
    slot = slot + NOB;
    x_slot = slot;
    slot = slot + NOB;
    y_slot = slot;
    slot = slot + NOB;
    counter_slot = slot;
    slot = slot + NOB;
    cycles_slot = slot;
    slot = slot + NOB;
    dx_slot = slot;
    slot = slot + NOB;
    dy_slot = slot;
    slot = slot + NOB;
    angular_momentum_slot = slot;
    slot = slot + SHIPS;
    angle_slot = slot;
    slot = slot + SHIPS;
    fuel_slot = slot;
    slot = slot + SHIPS;
    torpedoes_slot = slot;
    slot = slot + SHIPS;
    outline_slot = slot;
    slot = slot + SHIPS;
    previous_control_slot = slot;
    slot = slot + SHIPS;
    saved_routine_slot = slot;
    slot = slot + SHIPS;
    jumps_left_slot = slot;
    slot = slot + SHIPS;
    recharge_slot = slot;
    slot = slot + SHIPS;
    uncertainty_slot = slot;

    if ((first_spaceship ^ ROUTINES[0]) != 0)
        goto game_ending;
    if ((second_spaceship ^ ROUTINES[1]) != 0)
        goto game_ending;
    if (1 + TORPEDOES[0] < 0)
        goto playing;
    if (SKIPNOT(1 + TORPEDOES[1] >= 0))
        goto game_ending;
playing:
    restart_delay = torpedo_life() << 1;
    return objects();

game_ending:
    if (++restart_delay < 0)
        return objects();
    /* Score the survivors. Program flags 1 and 2 show which ship survived,
     * but flag 2 is cleared again at once, and nothing reads them. */
    stf(1);
    stf(2);
    word gone = first_spaceship ^ ROUTINES[0];
    if (gone != 0)
        clf(1);
    if (gone == 0)
        ++first_score;
    gone = second_spaceship ^ ROUTINES[1];
    if (gone != 0)
        clf(2);
    if (gone == 0)
        ++second_score;
    clf(2);
    return between_games();
}

/* ------------------------------------------------- starting and scoring */

/* a1, from start at 5: read the test word switches as the control word. */
BLOCK SYM("a1") void start_with_test_word(void)
{
    control_word_getter = read_test_word;
    return between_games();
}

/* a40, from start at 4: read the control boxes, through the control word
 * routine. */
BLOCK SYM("a40") void start_with_control_boxes(void)
{
    control_word_getter = control_word_routine;
    return new_match();
}

/* a: after a game. In a match the game count steps on, and a tie at the
 * end adds a game. The scores show on the console lights, ship 1's in AC
 * and ship 2's in IO, while the machine halts: after every game with test
 * word switch 040 on, else at the end of a match. Continuing with the
 * switch off clears them and starts a new match (a4, a5). */
BLOCK void between_games(void)
{
    if (games_left >= 0)
        goto ask;
    if (++games_left < 0)
        goto ask;
    if (first_score != second_score)
        goto show_scores;
    games_left = -1;
ask:
    if ((lat() & 040) == 0)
        return new_game();
show_scores:
    word first = first_score;
    register word second = second_score;
    halt(first, second);
    if ((lat() & 040) != 0)
        return new_game();
    first_score = 0;
    second_score = 0;
    return new_match();
}

/* a6: a match. The five test word switches above the scores switch give
 * the number of games. */
BLOCK void new_match(void)
{
    word games = lat();
    games = rar(games, 6) & 037;
    if (games != 0)
        games = -games;
    games_left = games;
    return new_game();
}

/* a2: a new game. Clear the whole object table, put the ships in opposite
 * corners with the needle turned around, and compile their outlines into
 * the free core after the table. When separate_outlines is +0 both ships
 * share one outline, the wedge, which leaves room for ddt (a3). */
BLOCK void new_game(void)
{
    clearing = ROUTINES;
clear:
    *home(clearing) = 0;
    if (I_DZM(++clearing) != I_DZM(COMPILED_OUTLINES))
        goto clear;

    ROUTINES[0] = first_spaceship;
    ROUTINES[1] = second_spaceship;
    word corner = 0200000;
    X_POSITIONS[0] = corner;
    Y_POSITIONS[0] = corner;
    corner = -corner;
    X_POSITIONS[1] = corner;
    Y_POSITIONS[1] = corner;
    ANGLES[0] = 0144420;            /* pi */

    word *code = COMPILED_OUTLINES;
    OUTLINES[0] = (word)code;
    register word separate = separate_outlines;
    if (separate >= 0)
        goto second;
    code = outline_compiler(code, needle_outline);
second:
    OUTLINES[1] = (word)code;
    outline_compiler(code, wedge_outline);

    word supply = torpedo_supply();
    TORPEDOES[0] = supply;
    TORPEDOES[1] = supply;
    supply = fuel_supply;
    FUEL[0] = supply;
    FUEL[1] = supply;
    supply = 02000;
    CYCLES[0] = supply;
    CYCLES[1] = supply;
    supply = hyperspace_shots();
    JUMPS_LEFT[0] = supply;
    JUMPS_LEFT[1] = supply;
    return next_frame();
}

/* ------------------------------------------------ control word getters */

/* mg1: the control boxes. IO is cleared, then read from the boxes. */
JSP SYM("mg1") io_word read_control_boxes(register word io)
{
    io = 0;
    io = control_boxes();
    return io;
}

/* mg2: the test word switches, swapped into IO. */
JSP io_word read_test_word(register word io)
{
    word switches = lat();
    rcl(switches, io, 18);
    return io;
}

/* ---------------------------------------------------------- the objects */

/* ml1: the object loop. Each active object that can collide is tested
 * against every later object that can: both explode when they come within
 * an octagon around each other, |dx| and |dy| below collision_radius and
 * |dx| + |dy| below collision_radius plus half of it. The explosion lasts
 * longer the more time the two calc routines take: longest for two ships,
 * shortest for two torpedoes. Then the object's calc routine runs, and its
 * time is charged to the frame (mq4). The last object has no later one to
 * test (mq3 after it). */
BLOCK void objects(void)
{
object:
    word routine = *home(routine_slot);
    if (routine == 0)
        goto next_object;
    register word calc = SWAP(routine);
    ++objects_seen;
    if (calc < 0)
        goto run;

    other_routine_slot = 1 + routine_slot;
    other_x_slot = 1 + x_slot;
    other_y_slot = 1 + y_slot;
    other_counter_slot = 1 + counter_slot;
    other_cycles_slot = 1 + cycles_slot;
    draw_outline = (compiled_outline *)*home(outline_slot);
compare:
    word other = *home(other_routine_slot);
    if (other <= 0)
        goto next_other;
    word dx = *home(x_slot) - *home(other_x_slot);
    if (dx < 0)
        dx = -dx;
    distance_x = dx;
    if (dx - collision_radius >= 0)
        goto next_other;
    word dy = *home(y_slot) - *home(other_y_slot);
    if (dy < 0)
        dy = -dy;
    dy = dy - collision_radius;
    if (dy >= 0)
        goto next_other;
    if (dy + distance_x - collision_radius_half >= 0)
        goto next_other;
    word bang = explosion | NON_COLLIDING;
    *routine_slot = bang;
    *other_routine_slot = bang;
    word frames = *cycles_slot + *home(other_cycles_slot);
    frames = (-frames >> 8) + 1;
    *home(counter_slot) = frames;
    *home(other_counter_slot) = frames;
next_other:
    ++other_x_slot;
    ++other_y_slot;
    ++other_counter_slot;
    ++other_cycles_slot;
    if (I_LAC(++other_routine_slot) != I_LAC(ROUTINES + NOB))
        goto compare;

run:
    ((calc_routine *)*routine_slot)();
    spare_time = *home(cycles_slot) + spare_time;
next_object:
    ++x_slot;
    ++y_slot;
    ++counter_slot;
    ++cycles_slot;
    ++dx_slot;
    ++dy_slot;
    ++angular_momentum_slot;
    ++angle_slot;
    ++stray_cursor;
    ++fuel_slot;
    ++torpedoes_slot;
    ++outline_slot;
    ++previous_control_slot;
    ++saved_routine_slot;
    ++jumps_left_slot;
    ++recharge_slot;
    ++uncertainty_slot;
    if (I_LAC(++routine_slot) != I_LAC(ROUTINES + (NOB - 1)))
        goto object;

    routine = *routine_slot;
    if (routine == 0)
        goto heavens;
    ((calc_routine *)routine)();
    spare_time = *cycles_slot + spare_time;
heavens:
    expensive_planetarium();
    central_star();
spare:
    if (++spare_time < 0)           /* the spare-time loop: burn the rest of the frame */
        goto spare;
    return next_frame();
}

REGION_BREAK();

/* ------------------------------------------- after the code: core layout */

CONSTANTS();                        /* the literal constants */
VARIABLES();                        /* the pool words */
RESERVE word patch_space[0200];
RESERVE word object_table[TABLE_WORDS] SYM("mtb");
