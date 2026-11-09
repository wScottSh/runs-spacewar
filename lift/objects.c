/* Calc routines for objects that are not flying spaceships (source lines
 * 946-1077): the explosion, the torpedo, and a ship in hyperspace and at
 * breakout.
 *
 * A calc routine is what the object table's routine word names. The main
 * loop calls the current object's routine each frame, with the cursors of
 * object_table.h on that object's slots; the routine moves the object,
 * draws it, and may hand the object to another routine by storing that
 * routine's address in the routine word. */

#include "object_table.h"
#include "random.h"
#include "inertia.h"

extern word hyperspatial_uncertainty;
XCT word torpedo_space_warpage(word position);
XCT word breakout_time(void);
XCT word hyperfield_recharge_time(void);
XCT dword hyperspatial_displacement(word high, register word low);
XCT dword hyperspatial_velocity(word high, register word low);

#define TWO_PI 0311040              /* an angle's full turn */

/* ---------------------------------------------------------- explosion */

POOL word particles;                /* particles still to draw this frame, counting up */

/* A particle's spread from the object, set for each particle: a right
 * shift of AC:IO, run through a pointer held in the xct that runs it, then
 * a random left shift built for the particle and run where it stands. */
HOMED const shift *spread_scale;
HOMED shift particle_shift = SHIFT_UNSET;
extern shift spread_scales[2];

/* An exploding object keeps drifting and is drawn as a cloud of dots, one
 * per 8 instructions of its calc routine's time, for as many frames as its
 * counter has left; then its slot is freed. */
JSP void explosion(void)  /* mex */
{
    word particle_count;
    dword dot;

    move_x(0);
    move_y(0);
    spread_scale = spread_scales;
    particle_count = *cycles_slot;
    particle_count = -particle_count, dot.lo = 0;
    particle_count = particle_count >> 3;
    particles = particle_count;
    /* Meant to give a big explosion the wider spread, but particle_count is
     * negative here, so the test never passes (Inside Spacewar! part 7). */
    if (particle_count - 0140 >= 0)
        ++spread_scale;
particle:
    particle_shift = I_SCL_BITS(next_random() & 0777);
    dot.hi = next_random();
    scr(dot.hi, dot.lo, 9);             /* a random half in each register */
    dot.lo = dot.lo >> 9;
    dot = xct(*home(spread_scale), dot.hi, dot.lo);
    dot = xct(particle_shift, dot.hi, dot.lo);
    dot.hi = dot.hi + *y_slot;
    rcl(dot.hi, dot.lo, 18);            /* swap: x into AC, y into IO */
    dot.hi = dot.hi + *x_slot;
    dpy(dot.hi, dot.lo, 3);
    if (++particles < 0)
        goto particle;
    if (++*counter_slot < 0)
        return;
    *routine_slot = 0;
}

shift spread_scales[2] = { I_SCR(1), I_SCR(3) };

/* ------------------------------------------------------------ torpedo */

/* A torpedo flies straight, bent only by the torpedo space warpage (each
 * velocity takes a little of the other axis's position), until its life
 * runs out and it explodes. */
JSP void torpedo(void)  /* tcr */
{
    word coordinate;

    if (++*counter_slot < 0)
        goto fly;
    *routine_slot = explosion | NON_COLLIDING;
    *counter_slot = -2;
    return;
fly:
    coordinate = *x_slot >> 9;
    coordinate = move_y(torpedo_space_warpage(coordinate));
    coordinate = coordinate >> 9;
    coordinate = move_x(torpedo_space_warpage(coordinate));
    register word dot_y = *y_slot;
    dpy(coordinate, dot_y, 1);
}

/* --------------------------------------------------------- hyperspace */

JSP void breakout(void);

POOL word angle_steps;              /* passes left to bring the new heading within a turn */

/* A ship in hyperspace is not drawn and does not collide. When its time is
 * up it jumps by a random displacement, takes a random velocity and
 * heading, and breakout begins. IO holds whatever the main loop left
 * there; shifting a random number in pushes it out. */
JSP void in_hyperspace(register word io)  /* hp1 */
{
    word random_high;                   /* a random number's high half */
    word heading;
    dword scaled;                       /* a random pair, scaled: the jump, then the velocity */

    if (++*counter_slot < 0)
        return;
    *routine_slot = breakout;
    *cycles_slot = 7;
    random_high = next_random();
    scr(random_high, io, 9);            /* a random half in each register */
    io = io >> 9;
    scaled = hyperspatial_displacement(random_high, io);
    scaled.hi = scaled.hi + *x_slot;
    *x_slot = scaled.hi;
    rcl(scaled.hi, scaled.lo, 18);      /* swap */
    scaled.hi = scaled.hi + *y_slot;
    *y_slot = scaled.hi;
    random_high = next_random();
    scr(random_high, scaled.lo, 9);
    scaled.lo = scaled.lo >> 9;
    scaled = hyperspatial_velocity(random_high, scaled.lo);
    *dy_slot = scaled.hi;
    *dx_slot = scaled.lo;
    angle_steps = -3;
    *angle_slot = random_number;
turn:
    heading = *angle_slot;
    if (heading >= 0)
        heading = heading - TWO_PI;
    if (heading < 0)
        heading = heading + TWO_PI;
    *angle_slot = heading;
    if (++angle_steps < 0)
        goto turn;
    *counter_slot = breakout_time();
}

/* Breakout: the ship shows as a dot and can collide again. When its time
 * is up it gets its own calc routine back, uses up a jump, starts the
 * hyperfield generators' recharge and takes on more uncertainty; then it
 * survives only if a random number outweighs the uncertainty. */
JSP void breakout(void)
{
    word uncertainty;
    word dot_x;
    register word dot_y;

    if (++*counter_slot < 0)
        goto show;
    *routine_slot = *saved_routine_slot;
    *cycles_slot = 02000;
    if (++*jumps_left_slot < 0)
        goto recharge;
    *jumps_left_slot = 0;
recharge:
    *recharge_slot = hyperfield_recharge_time();
    uncertainty = *uncertainty_slot + hyperspatial_uncertainty;
    *uncertainty_slot = uncertainty;
    if ((next_random() | 0400000) + *uncertainty_slot < 0)
        return;
    *routine_slot = explosion | NON_COLLIDING;
    *counter_slot = -010;
    *cycles_slot = 02000;
show:
    dot_x = *x_slot;
    dot_y = *y_slot;
    dpy(dot_x, dot_y, 2);
}
