/* The object table and the main loop's cursors into it.
 *
 * Each property of the game's objects (the two spaceships and their
 * torpedoes) is an array in the object table, one slot per object. Each
 * frame the main loop walks the objects and calls the current one's calc
 * routine with every cursor pointing at that object's slots, so a calc
 * routine works on "the current object" through these pointers. Most
 * cursors are the address fields of instructions in the main loop and the
 * spaceship calc routine; the rest are pool words. Their homes are in
 * that code, so here they are declared, not defined. */
#ifndef OBJECT_TABLE_H
#define OBJECT_TABLE_H

/* The calc routine word: 0 when the slot is free, otherwise the address of
 * the object's calc routine, with the sign bit set when the object does not
 * collide (exploding, or in hyperspace). */
extern HOMED word *routine_slot;  /* ml1 */
#define NON_COLLIDING ((word)0400000)
#define COLLIDING ((word)0)

/* The table itself: one array per property, NOB slots each, the routine
 * words first. */
extern word object_table[];  /* mtb */

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

extern HOMED word *x_slot;           /* mx1: position */
extern HOMED word *y_slot;  /* my1 */
extern POOL word *dx_slot;           /* mdx: velocity */
extern POOL word *dy_slot;  /* mdy */
extern HOMED word *counter_slot;     /* ma1: frames left: the life of a torpedo or an
                                                   explosion, the time in hyperspace */
extern HOMED word *cycles_slot;      /* mb1: the time the calc routine takes, in
                                                   instructions, and the size of an explosion */

/* Spaceships only. */
extern HOMED word *angle_slot;       /* mth: heading */
extern HOMED word *angular_momentum_slot;  /* mom */
extern POOL word *fuel_slot;         /* mfu: fuel, counting up: out at 0 */
extern POOL word *torpedoes_slot;    /* mtr: torpedoes left, counting up */
extern HOMED word *previous_control_slot;    /* mco: the control word last frame */
extern POOL word *saved_routine_slot;    /* mh1: the ship's own calc routine, kept
                                                       while hyperspace runs instead */
extern POOL word *jumps_left_slot;   /* mh2: hyperspace jumps left, counting up */
extern POOL word *recharge_slot;     /* mh3: hyperfield generator recharge, counting up */
extern POOL word *uncertainty_slot;  /* mh4: hyperspatial uncertainty: the risk that
                                                   the next breakout destroys the ship */

#endif
