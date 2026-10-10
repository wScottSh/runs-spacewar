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

extern word hyperspatial_uncertainty SYM("hur");
XCT SYM("the") word torpedo_space_warpage(word v);
XCT SYM("hd2") word breakout_time(void);
XCT SYM("hd3") word hyperfield_recharge_time(void);
XCT SYM("hr1") dword hyperspatial_displacement(word hi, register word lo);
XCT SYM("hr2") dword hyperspatial_velocity(word hi, register word lo);

#define TWO_PI 0311040              /* an angle's full turn */

/* ---------------------------------------------------------- explosion */

POOL word particles;                /* particles still to draw this frame, counting up */

/* A particle's spread from the object, set for each particle: a right
 * shift of AC:IO, run through a pointer held in the xct that runs it, then
 * a random left shift built for the particle and run where it stands. */
HOMED const insn *spread_scale;
HOMED insn particle_shift = I_HLT;
extern insn spread_scales[2];

/* An exploding object keeps drifting and is drawn as a cloud of dots, one
 * per 8 instructions of its calc routine's time, for as many frames as its
 * counter has left; then its slot is freed. */
JSP SYM("mex") void explosion(void)
{
    word count;
    dword spot;

    move_x(0);
    move_y(0);
    spread_scale = spread_scales;
    count = *cycles_slot;
    count = -count, spot.lo = 0;
    count = count >> 3;
    particles = count;
    /* Meant to give a big explosion the wider spread, but count is
     * negative here, so the test never passes (Inside Spacewar! part 7). */
    if (count - 0140 >= 0)
        ++spread_scale;
particle:
    particle_shift = (next_random() & 0777) | I_SCL(0);
    spot.hi = next_random();
    scr(spot.hi, spot.lo, 9);           /* a random half in each register */
    spot.lo = spot.lo >> 9;
    spot = xct(*home(spread_scale), spot.hi, spot.lo);
    spot = xct(particle_shift, spot.hi, spot.lo);
    spot.hi = spot.hi + *y_slot;
    rcl(spot.hi, spot.lo, 18);          /* swap: x into AC, y into IO */
    spot.hi = spot.hi + *x_slot;
    dpy(spot.hi, spot.lo, 3);
    if (++particles < 0)
        goto particle;
    if (++*counter_slot < 0)
        return;
    *routine_slot = 0;
}

insn spread_scales[2] = { I_SCR(1), I_SCR(3) };

/* ------------------------------------------------------------ torpedo */

/* A torpedo flies straight, bent only by the torpedo space warpage (each
 * velocity takes a little of the other axis's position), until its life
 * runs out and it explodes. */
JSP SYM("tcr") void torpedo(void)
{
    word a;

    if (++*counter_slot < 0)
        goto fly;
    *routine_slot = explosion | NON_COLLIDING;
    *counter_slot = -2;
    return;
fly:
    a = *x_slot >> 9;
    a = move_y(torpedo_space_warpage(a));
    a = a >> 9;
    a = move_x(torpedo_space_warpage(a));
    register word y = *y_slot;
    dpy(a, y, 1);
}

/* --------------------------------------------------------- hyperspace */

JSP void breakout(void);

POOL word angle_steps;              /* passes left to bring the new heading within a turn */

/* A ship in hyperspace is not drawn and does not collide. When its time is
 * up it jumps by a random displacement, takes a random velocity and
 * heading, and breakout begins. IO holds whatever the main loop left
 * there; shifting a random number in pushes it out. */
JSP SYM("hp1") void in_hyperspace(register word io)
{
    word r;
    dword d;

    if (++*counter_slot < 0)
        return;
    *routine_slot = breakout;
    *cycles_slot = 7;
    r = next_random();
    scr(r, io, 9);                      /* a random half in each register */
    io = io >> 9;
    d = hyperspatial_displacement(r, io);
    d.hi = d.hi + *x_slot;
    *x_slot = d.hi;
    rcl(d.hi, d.lo, 18);                /* swap */
    d.hi = d.hi + *y_slot;
    *y_slot = d.hi;
    r = next_random();
    scr(r, d.lo, 9);
    d.lo = d.lo >> 9;
    d = hyperspatial_velocity(r, d.lo);
    *dy_slot = d.hi;
    *dx_slot = d.lo;
    angle_steps = -3;
    *angle_slot = random_number;
turn:
    r = *angle_slot;
    if (r >= 0)
        r = r - TWO_PI;
    if (r < 0)
        r = r + TWO_PI;
    *angle_slot = r;
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
    word a;
    register word y;

    if (++*counter_slot < 0)
        goto show;
    *routine_slot = *saved_routine_slot;
    *cycles_slot = 02000;
    if (++*jumps_left_slot < 0)
        goto recharge;
    *jumps_left_slot = 0;
recharge:
    *recharge_slot = hyperfield_recharge_time();
    a = *uncertainty_slot + hyperspatial_uncertainty;
    *uncertainty_slot = a;
    if ((next_random() | 0400000) + *uncertainty_slot < 0)
        return;
    *routine_slot = explosion | NON_COLLIDING;
    *counter_slot = -010;
    *cycles_slot = 02000;
show:
    a = *x_slot;
    y = *y_slot;
    dpy(a, y, 2);
}
