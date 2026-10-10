/* The spaceship calc routine (source lines 1079-1333): a ship turns,
 * thrusts and falls toward the central star, is drawn by its compiled
 * outline with an exhaust flame behind it, fires torpedoes and jumps into
 * hyperspace. The main loop calls it once a frame for each live ship, with
 * the cursors of object_table.h on that ship's slots.
 *
 * Its code hands control on by jumps, so its functions end in tail calls;
 * every path leaves through spaceship_done, the source's `srt`. */

#include "object_table.h"
#include "control_word.h"
#include "random.h"
#include "star_vector.h"
#include "inertia.h"

#define TWO_PI 0311040              /* an angle's full turn */
#define THRUST_FLAG 6               /* set while the ship fires its rocket and has fuel */

POOL word control_word;             /* this ship's controls, in the high four bits */

/* Tunables (lift/tunables.c). */
extern word angular_acceleration;
extern word star_capture_radius;
XCT word spaceship_acceleration(word heading);
XCT word torpedo_velocity(word heading);
XCT word torpedo_reload_time(void);
XCT word torpedo_life(void);
XCT word time_before_breakout(void);

/* Arithmetic. integer_divide returns past one more word unless the
 * quotient overflows (lift/divide.c). */
JDA word sine(word angle);
JDA word cosine(word angle);
JDA word integer_multiply(word a, BYNAME word b);
JDA dword multiply(word a, BYNAME word b);
JDA word square_root(word remainder);
JDA SKIPS dword integer_divide(word dividend, register word low, BYNAME word divisor);

/* Calc routines a ship hands its object over to. */
JSP void explosion(void);
JSP void torpedo(void);
JSP void in_hyperspace(register word io);

/* Cursors whose homes are in this routine (HOMED in object_table.h). */
word *angular_momentum_slot;        /* mom */
word *angle_slot;                   /* mth */
word *previous_control_slot;        /* mco */

POOL word heading_sine;
POOL word heading_cosine;

/* Gravity: the pull toward the central star added to the velocity this
 * frame, in the words the central star's display also uses. */
#define gravity_x star_vector_x
#define gravity_y star_vector_y
POOL word gravity_operand;          /* the operand of each step: a scaled coordinate,
                                       then the squared distance, then the divisor */
POOL word ship_x_squared;

/* Pool words the compiled outline (lift/outline_compiler.c) draws the ship from. */
extern POOL word ship_x;
extern POOL word ship_y;
extern POOL word down_step_x;
extern POOL word down_step_y;
extern POOL word out_step_x;
extern POOL word out_step_y;
extern POOL word out_down_step_x;
extern POOL word out_down_step_y;
extern POOL word in_down_step_x;
extern POOL word in_down_step_y;
POOL word torpedo_start_x;          /* just in front of the ship's tip */
POOL word torpedo_start_y;
POOL word flame_length;             /* exhaust dots still to draw, counting up */

/* The ship's compiled outline. The main loop stores its address here each
 * frame, in the jump that enters it; the code ends by jumping back to
 * outline_drawn. */
typedef void compiled_outline(void) BLOCK;
HOMED compiled_outline *draw_outline;  /* sp5 */

/* The free slot a new torpedo takes, and the new torpedo's slots. */
HOMED word *free_slot;
HOMED word *torpedo_x_slot;
HOMED word *torpedo_y_slot;
HOMED word *torpedo_counter_slot;
HOMED word *torpedo_cycles_slot;
HOMED word *torpedo_dx_slot;
HOMED word *torpedo_dy_slot;

BLOCK void spaceship(void);
BLOCK void outline_drawn(void);
BLOCK void spaceship_done(void);
BLOCK void spaceship_in_star(void);

/* The second ship's bits are the low four; rotating them up makes them
 * read as the first ship's. */
JSP void first_spaceship(void)  /* ss1 */
{
    register word controls = control_word_getter();
    control_word = controls;
    return spaceship();
}

JSP void second_spaceship(void)  /* ss2 */
{
    register word controls = control_word_getter();
    controls = rir(controls, 4);
    control_word = controls;
    return spaceship();
}

BLOCK void spaceship(void)
{
    register word controls = control_word;
    word turn;
    word push;
    word angle;
    word capture_margin;                /* the squared distance less the capture radius */
    dword distance_cubed;
    dword pull;

    /* Rotation. With sense switch 1 on, the rotate buttons work through
     * angular momentum, which builds up; otherwise they turn the ship
     * directly, faster. */
    clf(THRUST_FLAG), turn = 0;
    if (controls < 0)
        turn = turn + angular_acceleration;
    controls = ril(controls, 1);
    if (controls < 0)
        turn = turn - angular_acceleration;
    turn = turn + *home(angular_momentum_slot);
    *angular_momentum_slot = turn;
    if (sense(1))
        goto thrust;
    *angular_momentum_slot = 0;
    turn = ral(turn, 7);
thrust:
    controls = ril(controls, 1);
    if (controls < 0)
        stf(THRUST_FLAG);
    register word fuel = *fuel_slot;
    if (fuel >= 0)
        clf(THRUST_FLAG);

    angle = turn + *home(angle_slot);
    if (angle >= 0)
        angle = angle - TWO_PI;
    if (angle < 0)
        angle = angle + TWO_PI;
    *angle_slot = angle;
    heading_sine = sine(angle);

    /* Gravity, unless sense switch 6 removes the star: the pull is the
     * position over the cube of the distance from the star (each
     * coordinate scaled down by 2^11). Closer than the capture radius,
     * the ship falls into the star. Sense switch 2 makes the star light. */
    gravity_x = 0;
    gravity_y = 0;
    if (sense(6))
        goto accelerate;
    gravity_operand = *x_slot >> 11;
    ship_x_squared = integer_multiply(gravity_operand, gravity_operand);
    gravity_operand = *y_slot >> 11;
    capture_margin = integer_multiply(gravity_operand, gravity_operand) + ship_x_squared - star_capture_radius;
    if (capture_margin <= 0)
        return spaceship_in_star();
    gravity_operand = capture_margin + star_capture_radius;
    distance_cubed = multiply(square_root(gravity_operand) >> 9, gravity_operand);
    scr(distance_cubed.hi, distance_cubed.lo, 2);
    if (!sense(2))
        scr(distance_cubed.hi, distance_cubed.lo, 2);
    if (distance_cubed.hi != 0)
        goto accelerate;                /* too far for gravity to tell */
    gravity_operand = distance_cubed.lo;
    pull = integer_divide(-*x_slot, distance_cubed.lo, gravity_operand);
    gravity_x = pull.hi;
    pull = integer_divide(-*y_slot, pull.lo, gravity_operand);
    gravity_y = pull.hi;

accelerate:
    if (0 == *fuel_slot)
        clf(THRUST_FLAG);
    heading_cosine = cosine(*angle_slot);
    push = spaceship_acceleration(heading_cosine >> 9);
    if (!flag(THRUST_FLAG))
        push = 0;
    move_y(push + gravity_y);
    push = -spaceship_acceleration(heading_sine >> 9);
    if (!flag(THRUST_FLAG))
        push = 0;
    move_x(push + gravity_x);

    /* The outline starts at the tip, a 32nd of the heading ahead, and a
     * torpedo starts as far again. The steps the outline is drawn with
     * are the heading scaled down by 2^9, turned to each direction. */
    down_step_x = heading_sine >> 5;
    down_step_y = heading_cosine >> 5;
    ship_x = *x_slot - down_step_x;
    torpedo_start_x = ship_x - down_step_x;
    ship_y = *y_slot + down_step_y;
    torpedo_start_y = ship_y + down_step_y;
    down_step_x = heading_sine >> 9;
    down_step_y = heading_cosine >> 9;
    out_step_y = down_step_x;
    out_down_step_x = out_step_y + down_step_y;
    in_down_step_y = out_down_step_x;
    in_down_step_x = down_step_x - down_step_y;
    out_down_step_y = -in_down_step_x;
    out_step_x = down_step_y;

    /* A dot at the center that asks for a completion pulse, so the
     * outline's first wait for the display ends. */
    dword dot;
    dot.hi = 0, dot.lo = 0;
    dpy_nowait(dot.hi, dot.lo);
    return (*home(draw_outline))();
}

/* Entered from the last word of the compiled outline: the jump back here
 * that the outline compiler writes (`*code++ = I_JMP(outline_drawn)`). */
BLOCK void outline_drawn(void)  /* sq6 */
{
    word flame_dots;
    word fire;
    register word controls;
    register word dot_y;
    register word launch_coordinate;

    /* The exhaust flame: a random number of dots behind the tail while
     * the rocket fires, each burning a unit of fuel. */
    ioh();
    flame_dots = next_random() >> 13;
    if (flame_dots >= 0)
        flame_dots = -flame_dots;
    flame_length = flame_dots;
    controls = control_word;
    controls = ril(controls, 2);
    if (controls >= 0)
        goto torpedoes;
flame:
    down_step_x = heading_sine >> 8;
    down_step_y = heading_cosine >> 8;
    if (++*fuel_slot < 0)
        goto flame_dot;
    *fuel_slot = 0;
    goto torpedoes;
flame_dot:
    ship_y = ship_y - down_step_y;
    ship_x = ship_x + down_step_x;
    dot_y = ship_y;
    dpy(ship_x, dot_y, 0);
    if (++flame_length < 0)
        goto flame;

    /* Torpedoes. The counter is the tube's reload time. The fire button
     * launches while held; with sense switch 3 on, only when newly pressed
     * (but the previous control word is never stored, so it is always
     * newly pressed). */
torpedoes:
    if (++*counter_slot < 0)
        goto hyperspace;
    *counter_slot = 0;
    fire = ~*home(previous_control_slot);
    if (!sense(3))
        fire = MINUS_ZERO;
    fire = fire & control_word;
    fire = ral(fire, 3);
    if (fire >= 0)
        goto hyperspace;
    if (++*torpedoes_slot < 0)
        goto launch;
    *torpedoes_slot = 0;                /* out of torpedoes */
    goto hyperspace;

    /* A new torpedo takes the first free slot of the object table. Its
     * slots are the free slot's in each property array after the first. */
launch:
    free_slot = object_table;
search:
    if (*home(free_slot) == 0)
        goto found;
    if (I_LAC(++free_slot) != I_LAC(object_table + OBJECT_COUNT))
        goto search;
    for (;;)
        hlt();                          /* no space for new objects */
found:
    *free_slot = torpedo | COLLIDING;
    torpedo_x_slot = OBJECT_COUNT + free_slot;
    launch_coordinate = torpedo_start_x;
    *home(torpedo_x_slot) = launch_coordinate;
    torpedo_y_slot = torpedo_x_slot + OBJECT_COUNT;
    launch_coordinate = torpedo_start_y;
    *home(torpedo_y_slot) = launch_coordinate;
    torpedo_counter_slot = torpedo_y_slot + OBJECT_COUNT;
    torpedo_cycles_slot = torpedo_counter_slot + OBJECT_COUNT;
    torpedo_dx_slot = torpedo_cycles_slot + OBJECT_COUNT;
    torpedo_dy_slot = torpedo_dx_slot + OBJECT_COUNT;
    *home(torpedo_dx_slot) = -torpedo_velocity(heading_sine) + *dx_slot;
    *home(torpedo_dy_slot) = torpedo_velocity(heading_cosine) + *dy_slot;
    *counter_slot = torpedo_reload_time();
    *home(torpedo_counter_slot) = torpedo_life();
    home(torpedo_cycles_slot)->addr = 020;  /* the torpedo calc's length */

    /* Hyperspace: both rotate buttons newly pressed, the hyperfield
     * generators recharged and jumps left. The ship's calc routine is
     * kept while in_hyperspace runs instead. */
hyperspace:
    if (++*recharge_slot < 0)
        goto done;
    *recharge_slot = 0;
    if (*jumps_left_slot == 0)
        goto done;
    if (((~control_word | *previous_control_slot) & 0600000) != 0)
        goto done;
    *saved_routine_slot = *routine_slot;
    *routine_slot = in_hyperspace | NON_COLLIDING;
    *counter_slot = time_before_breakout();
    *cycles_slot = 3;
done:
    return spaceship_done();
}

BLOCK void spaceship_done(void)
{
}

/* A ship that falls into the central star stops. With sense switch 5 on
 * it explodes; otherwise it is thrown to the corner of the screen, and
 * instead of being drawn it counts up from its calc routine's time. A
 * ship's time is positive, so the count ends after one step. */
BLOCK void spaceship_in_star(void)
{
    word screen_corner;

    *dx_slot = 0;
    *dy_slot = 0;
    if (sense(5))
        goto explode;
    screen_corner = 0377777;
    *x_slot = screen_corner;
    *y_slot = screen_corner;
    down_step_x = *cycles_slot;         /* the pool word serves as the count */
wait:
    if (++down_step_x < 0)
        goto wait;
    return spaceship_done();
explode:
    *routine_slot = explosion | NON_COLLIDING;
    *counter_slot = -010;
    return spaceship_done();
}
