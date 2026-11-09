/* Inertia, the `diff` macro: the acceleration joins the velocity, and an
 * eighth of the velocity the position. The macro takes its scaling as an
 * instruction to run, here `sar 3s` from a constant. */
#ifndef INERTIA_H
#define INERTIA_H

static inline word move_x(word acceleration)
{
    word velocity = acceleration + *dx_slot;
    *dx_slot = velocity;
    word position = xct(I_SAR(3), velocity) + *x_slot;
    *x_slot = position;
    return position;
}

static inline word move_y(word acceleration)
{
    word velocity = acceleration + *dy_slot;
    *dy_slot = velocity;
    word position = xct(I_SAR(3), velocity) + *y_slot;
    *y_slot = position;
    return position;
}

#endif
