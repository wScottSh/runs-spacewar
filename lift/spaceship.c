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
XCT word spaceship_acceleration(word v);
XCT word torpedo_velocity(word v);
XCT word torpedo_reload_time(void);
XCT word torpedo_life(void);
XCT word time_before_breakout(void);

/* Arithmetic. integer_divide returns past one more word unless the
 * quotient overflows (lift/divide.c). */
JDA word sine(word angle);
JDA word cosine(word angle);
JDA word integer_multiply(word a, BYNAME word b);
JDA dword multiply(word a, BYNAME word b);
JDA word sqt(word r);
JDA SKIPS dword integer_divide(word dividend, register word lo, BYNAME word divisor);

/* Calc routines a ship hands its object over to. */
JSP void explosion(void);
JSP void torpedo(void);
JSP void in_hyperspace(register word io);

/* Cursors whose homes are in this routine (HOMED in object_table.h). */
word *angular_momentum_slot;  /* mom */
word *angle_slot;  /* mth */
word *previous_control_slot;  /* mco */

POOL word heading_sine;
POOL word heading_cosine;

/* Gravity: the pull toward the central star added to the velocity this
 * frame, in the words the central star's display also uses. */
#define gravity_x star_vector_x
#define gravity_y star_vector_y
POOL word work;                     /* a coordinate, then the squared distance, then the divisor */
POOL word ship_x_squared;

/* Pool words the compiled outline (lift/outline_compiler.c) draws the ship from. */
extern POOL word ship_x;
extern POOL word ship_y;
extern POOL word sine_step;
extern POOL word cosine_step;
extern POOL word out_x;
extern POOL word out_y;
extern POOL word out_down_x;
extern POOL word out_down_y;
extern POOL word in_down_x;
extern POOL word in_down_y;
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
    word d;
    dword f;
    dword q;

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
    work = *x_slot >> 11;
    ship_x_squared = integer_multiply(work, work);
    work = *y_slot >> 11;
    d = integer_multiply(work, work) + ship_x_squared - star_capture_radius;
    if (d <= 0)
        return spaceship_in_star();
    work = d + star_capture_radius;
    f = multiply(sqt(work) >> 9, work);
    scr(f.hi, f.lo, 2);
    if (!sense(2))
        scr(f.hi, f.lo, 2);
    if (f.hi != 0)
        goto accelerate;                /* too far for gravity to tell */
    work = f.lo;
    q = integer_divide(-*x_slot, f.lo, work);
    gravity_x = q.hi;
    q = integer_divide(-*y_slot, q.lo, work);
    gravity_y = q.hi;

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
    sine_step = heading_sine >> 5;
    cosine_step = heading_cosine >> 5;
    ship_x = *x_slot - sine_step;
    torpedo_start_x = ship_x - sine_step;
    ship_y = *y_slot + cosine_step;
    torpedo_start_y = ship_y + cosine_step;
    sine_step = heading_sine >> 9;
    cosine_step = heading_cosine >> 9;
    out_y = sine_step;
    out_down_x = out_y + cosine_step;
    in_down_y = out_down_x;
    in_down_x = sine_step - cosine_step;
    out_down_y = -in_down_x;
    out_x = cosine_step;

    /* A dot at the center that asks for a completion pulse, so the
     * outline's first wait for the display ends. */
    dword pen;
    pen.hi = 0, pen.lo = 0;
    dpy_nowait(pen.hi, pen.lo);
    return (*home(draw_outline))();
}

BLOCK void outline_drawn(void)  /* sq6 */
{
    word r;
    word fire;
    register word controls;
    register word y;
    register word start;

    /* The exhaust flame: a random number of dots behind the tail while
     * the rocket fires, each burning a unit of fuel. */
    ioh();
    r = next_random() >> 13;
    if (r >= 0)
        r = -r;
    flame_length = r;
    controls = control_word;
    controls = ril(controls, 2);
    if (controls >= 0)
        goto torpedoes;
flame:
    sine_step = heading_sine >> 8;
    cosine_step = heading_cosine >> 8;
    if (++*fuel_slot < 0)
        goto flame_dot;
    *fuel_slot = 0;
    goto torpedoes;
flame_dot:
    ship_y = ship_y - cosine_step;
    ship_x = ship_x + sine_step;
    y = ship_y;
    dpy(ship_x, y, 0);
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
    if (I_LAC(++free_slot) != I_LAC(object_table + NOB))
        goto search;
    for (;;)
        hlt();                          /* no space for new objects */
found:
    *free_slot = torpedo | COLLIDING;
    torpedo_x_slot = NOB + free_slot;
    start = torpedo_start_x;
    *home(torpedo_x_slot) = start;
    torpedo_y_slot = torpedo_x_slot + NOB;
    start = torpedo_start_y;
    *home(torpedo_y_slot) = start;
    torpedo_counter_slot = torpedo_y_slot + NOB;
    torpedo_cycles_slot = torpedo_counter_slot + NOB;
    torpedo_dx_slot = torpedo_cycles_slot + NOB;
    torpedo_dy_slot = torpedo_dx_slot + NOB;
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
    word corner;

    *dx_slot = 0;
    *dy_slot = 0;
    if (sense(5))
        goto bang;
    corner = 0377777;
    *x_slot = corner;
    *y_slot = corner;
    sine_step = *cycles_slot;
wait:
    if (++sine_step < 0)
        goto wait;
    return spaceship_done();
bang:
    *routine_slot = explosion | NON_COLLIDING;
    *counter_slot = -010;
    return spaceship_done();
}
