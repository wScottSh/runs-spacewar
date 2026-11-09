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
extern HOMED word *routine_slot;                /* ml1 */
#define NON_COLLIDING ((word)0400000)
#define COLLIDING ((word)0)

/* The table itself: one array per property, OBJECT_COUNT slots each, the
 * routine words first. */
extern word object_table[];                     /* mtb */

#define OBJECT_COUNT 030                        /* nob: objects in the table, two ships then torpedoes */
#define SHIPS 2
#define TABLE_WORDS (7 * OBJECT_COUNT + 10 * SHIPS)

/* Each property's array, where it starts in the object table. */
#define ROUTINES (object_table)
#define X_POSITIONS (ROUTINES + OBJECT_COUNT)                   /* nx1 */
#define Y_POSITIONS (X_POSITIONS + OBJECT_COUNT)                /* ny1 */
#define COUNTERS (Y_POSITIONS + OBJECT_COUNT)                   /* na1 */
#define CYCLES (COUNTERS + OBJECT_COUNT)                        /* nb1 */
#define DX_VELOCITIES (CYCLES + OBJECT_COUNT)                   /* ndx */
#define DY_VELOCITIES (DX_VELOCITIES + OBJECT_COUNT)            /* ndy */
#define ANGULAR_MOMENTA (DY_VELOCITIES + OBJECT_COUNT)          /* nom */
#define ANGLES (ANGULAR_MOMENTA + SHIPS)                        /* nth */
#define FUEL (ANGLES + SHIPS)                                   /* nfu */
#define TORPEDOES (FUEL + SHIPS)                                /* ntr */
#define OUTLINE_STARTS (TORPEDOES + SHIPS)                      /* not: each ship's compiled outline */
#define PREVIOUS_CONTROLS (OUTLINE_STARTS + SHIPS)              /* nco */
#define SAVED_ROUTINES (PREVIOUS_CONTROLS + SHIPS)              /* nh1 */
#define JUMPS_LEFT (SAVED_ROUTINES + SHIPS)                     /* nh2 */
#define RECHARGES (JUMPS_LEFT + SHIPS)                          /* nh3 */
#define UNCERTAINTIES (RECHARGES + SHIPS)                       /* nh4 */

/* Not a property: the free core after the table, where the outline
 * compiler writes the compiled outlines that OUTLINE_STARTS point into. */
#define OUTLINE_CODE_SPACE (UNCERTAINTIES + SHIPS)              /* nnn */

extern HOMED word *x_slot;                      /* mx1: position */
extern HOMED word *y_slot;                      /* my1 */
extern POOL word *dx_slot;                      /* mdx: velocity */
extern POOL word *dy_slot;                      /* mdy */
extern HOMED word *counter_slot;                /* ma1: frames left: the life of a torpedo or
                                                   an explosion, the time in hyperspace */
extern HOMED word *cycles_slot;                 /* mb1: the time the calc routine takes, in
                                                   instructions, and the size of an explosion */

/* Spaceships only. */
extern HOMED word *angle_slot;                  /* mth: heading */
extern HOMED word *angular_momentum_slot;       /* mom */
extern POOL word *fuel_slot;                    /* mfu: fuel, counting up: out at 0 */
extern POOL word *torpedoes_slot;               /* mtr: torpedoes left, counting up */
extern HOMED word *previous_control_slot;       /* mco: the control word last frame */
extern POOL word *saved_routine_slot;           /* mh1: the ship's own calc routine, kept
                                                   while hyperspace runs instead */
extern POOL word *jumps_left_slot;              /* mh2: hyperspace jumps left, counting up */
extern POOL word *recharge_slot;                /* mh3: hyperfield generator recharge, counting up */
extern POOL word *uncertainty_slot;             /* mh4: hyperspatial uncertainty: the risk that
                                                   the next breakout destroys the ship */

#endif
