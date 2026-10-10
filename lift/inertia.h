/* Inertia, the `diff` macro: the acceleration joins the velocity, and an
 * eighth of the velocity the position. The macro takes its scaling as an
 * instruction to run, here `sar 3s` from a constant. */
#ifndef INERTIA_H
#define INERTIA_H

static inline word move_x(word acceleration)
{
    word dx = acceleration + *dx_slot;
    *dx_slot = dx;
    word x = xct(I_SAR(3), dx) + *x_slot;
    *x_slot = x;
    return x;
}

static inline word move_y(word acceleration)
{
    word dy = acceleration + *dy_slot;
    *dy_slot = dy;
    word y = xct(I_SAR(3), dy) + *y_slot;
    *y_slot = y;
    return y;
}

#endif
