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
extern HOMED word *routine_slot SYM("ml1");
#define NON_COLLIDING ((word)0400000)

extern HOMED word *x_slot SYM("mx1");           /* position */
extern HOMED word *y_slot SYM("my1");
extern POOL word *dx_slot SYM("mdx");           /* velocity */
extern POOL word *dy_slot SYM("mdy");
extern HOMED word *counter_slot SYM("ma1");     /* frames left: the life of a torpedo or an
                                                   explosion, the time in hyperspace */
extern HOMED word *cycles_slot SYM("mb1");      /* the time the calc routine takes, in
                                                   instructions, and the size of an explosion */

/* Spaceships only. */
extern HOMED word *spin_slot SYM("mom");        /* angular velocity */
extern HOMED word *angle_slot SYM("mth");       /* heading */
extern POOL word *fuel_slot SYM("mfu");
extern POOL word *torpedoes_slot SYM("mtr");    /* torpedoes left, counting up */
extern HOMED word *old_control_slot SYM("mco"); /* last frame's control word */
extern POOL word *saved_routine_slot SYM("mh1");    /* the ship's own calc routine, kept
                                                       while hyperspace runs instead */
extern POOL word *jumps_left_slot SYM("mh2");   /* hyperspace jumps left, counting up */
extern POOL word *recharge_slot SYM("mh3");     /* hyperfield generator recharge, counting up */
extern POOL word *uncertainty_slot SYM("mh4");  /* hyperspatial uncertainty: the risk that
                                                   the next breakout destroys the ship */

#endif
