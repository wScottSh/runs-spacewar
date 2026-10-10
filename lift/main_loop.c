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
 * upon the other in one block (Inside Spacewar! part 3). The first
 * OBJECT_COUNT slots of each array are the objects; the spaceship-only
 * properties have a slot per ship. */

#include "object_table.h"
#include "control_word.h"

typedef void calc_routine(void) JSP;
typedef void compiled_outline(void) BLOCK;

/* Routines the main loop calls, defined elsewhere. */
JSP void first_spaceship(void);
JSP void second_spaceship(void);
JSP void explosion(void);
JSP void expensive_planetarium(void);
JSP void central_star(void);
JDA word *outline_compiler(word *code, INLINE const word *outline);
extern word needle_outline[8];
extern word wedge_outline[8];
JSP io_word control_word_routine(void);

XCT word torpedo_supply(void);
XCT word torpedo_life(void);
XCT word hyperspace_shots(void);
extern word fuel_supply;
extern word collision_radius;
extern word collision_radius_half;
extern word separate_outlines;

HOMED word *outline_slot;           /* mot: a ship's compiled outline, the code that draws it */
extern HOMED compiled_outline *draw_outline;  /* the spaceship calc routine's jump into it */

POOL control_word_reader *control_word_getter;  /* cwg */
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
BLOCK void start_with_test_word(void);
BLOCK void start_with_control_boxes(void);
BLOCK void between_games(void);
BLOCK void new_match(void);
BLOCK void new_game(void);
JSP io_word read_control_boxes(void);
JSP io_word read_test_word(void);

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

    /* The cursors in table order: each property's array follows the last,
     * so one pointer stepped by an array's length reaches every first slot. */
    word *slot = ROUTINES;
    routine_slot = slot;
    slot = slot + OBJECT_COUNT;
    x_slot = slot;
    slot = slot + OBJECT_COUNT;
    y_slot = slot;
    slot = slot + OBJECT_COUNT;
    counter_slot = slot;
    slot = slot + OBJECT_COUNT;
    cycles_slot = slot;
    slot = slot + OBJECT_COUNT;
    dx_slot = slot;
    slot = slot + OBJECT_COUNT;
    dy_slot = slot;
    slot = slot + OBJECT_COUNT;
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

    /* A ship whose routine word differs from its own calc routine in any
     * bit, the sign included, has exploded or is in hyperspace. */
    if ((first_spaceship ^ ROUTINES[0]) != 0)
        goto game_ending;
    if ((second_spaceship ^ ROUTINES[1]) != 0)
        goto game_ending;
    /* The torpedo counts run up toward 0; a ship can launch one more while
     * 1 + its count is still negative. */
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
    word routine_changed = first_spaceship ^ ROUTINES[0];
    if (routine_changed != 0)
        clf(1);
    if (routine_changed == 0)
        ++first_score;
    routine_changed = second_spaceship ^ ROUTINES[1];
    if (routine_changed != 0)
        clf(2);
    if (routine_changed == 0)
        ++second_score;
    clf(2);
    return between_games();
}

/* ------------------------------------------------- starting and scoring */

/* a1, from start at 5: read the test word switches as the control word. */
BLOCK void start_with_test_word(void)  /* a1 */
{
    control_word_getter = read_test_word;
    return between_games();
}

/* a40, from start at 4: read the control boxes, through the control word
 * routine. */
BLOCK void start_with_control_boxes(void)  /* a40 */
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
    word first_lights = first_score;
    register word second_lights = second_score;
    halt(first_lights, second_lights);
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
    if (I_DZM(++clearing) != I_DZM(OUTLINE_CODE_SPACE))
        goto clear;

    ROUTINES[0] = first_spaceship;
    ROUTINES[1] = second_spaceship;
    word start_corner = 0200000;
    X_POSITIONS[0] = start_corner;
    Y_POSITIONS[0] = start_corner;
    start_corner = -start_corner;
    X_POSITIONS[1] = start_corner;
    Y_POSITIONS[1] = start_corner;
    ANGLES[0] = 0144420;            /* pi */

    word *code = OUTLINE_CODE_SPACE;
    OUTLINE_STARTS[0] = (word)code;
    register word separate = separate_outlines;
    if (separate >= 0)
        goto second_outline;
    code = outline_compiler(code, needle_outline);
second_outline:
    OUTLINE_STARTS[1] = (word)code;
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
JSP io_word read_control_boxes(void)  /* mg1 */
{
    register word io = 0;
    io = control_boxes();
    return io;
}

/* mg2: the test word switches, swapped into IO. */
JSP io_word read_test_word(void)
{
    register word io = SWAP(lat());
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
    register word routine_sign = SWAP(routine);  /* negative: does not collide */
    ++objects_seen;
    if (routine_sign < 0)
        goto run;

    other_routine_slot = 1 + routine_slot;
    other_x_slot = 1 + x_slot;
    other_y_slot = 1 + y_slot;
    other_counter_slot = 1 + counter_slot;
    other_cycles_slot = 1 + cycles_slot;
    draw_outline = (compiled_outline *)*home(outline_slot);
compare:
    word other_routine = *home(other_routine_slot);
    if (other_routine <= 0)
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
    word exploding = explosion | NON_COLLIDING;
    *routine_slot = exploding;
    *other_routine_slot = exploding;
    word frames = *cycles_slot + *home(other_cycles_slot);
    frames = (-frames >> 8) + 1;
    *home(counter_slot) = frames;
    *home(other_counter_slot) = frames;
next_other:
    ++other_x_slot;
    ++other_y_slot;
    ++other_counter_slot;
    ++other_cycles_slot;
    if (I_LAC(++other_routine_slot) != I_LAC(ROUTINES + OBJECT_COUNT))
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
    if (I_LAC(++routine_slot) != I_LAC(ROUTINES + (OBJECT_COUNT - 1)))
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
