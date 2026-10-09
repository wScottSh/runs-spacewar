/* sin/cos -- Adams Associates (source lines 195-254).
 * Argument in AC, within +-2pi, binary point right of bit 3.
 * Answer has binary point right of bit 0.
 * cos shifts by pi/2 and enters sin's body past its prologue; both return
 * through the body's single exit. The body uses the two entry words as its
 * scratch cells. */
#include "spacewar.h"

#define HALF_PI 062210
#define TWO_PI  0311040
#define MAXPOS  0377777

ENTRY_CELL(cosine) word cos_cell;   /* cos's entry word */
ENTRY_CELL(sine)   word sin_cell;   /* sin's entry word */

BLOCK word sincos_body(word a);

JDA SYM("cos") word cosine(word c)
{
    sin_cell = HALF_PI + c;
    return sincos_body(sin_cell);
}

JDA SYM("sin") word sine(word s)
{
    return sincos_body(s);
}

BLOCK word sincos_body(word a)      /* a arrives in AC */
{
    /* reduce a to [0, pi/2] */
    if (a < 0)
si1:    a += TWO_PI;
    a -= HALF_PI;
    if (a >= 0)
        goto si2;
    a += HALF_PI;
si3:
    a = ral(a, 2);
    sin_cell = mpy(a, 0242763).hi;               /* x: scaled angle */
    cos_cell = mpy(sin_cell, sin_cell).hi;       /* x^2 */
    a = mpy(cos_cell, 0756103).hi + 0121312;     /* Horner in x^2 */
    a = mpy(a, cos_cell).hi + 0532511;
    a = mpy(a, cos_cell).hi + 0144417;
    {
        dword p = mpy(a, sin_cell);
        scl(p.hi, p.lo, 3);
        cos_cell = p.hi;
    }
    if ((cos_cell ^ sin_cell) < 0) {             /* overflowed: saturate */
        a = MAXPOS;
        if (sin_cell < 0)
            a = -a;
        return a;
    }
    return cos_cell;

si2:                                             /* a was in (pi/2, ...] */
    a = -a + HALF_PI;
    if (a >= 0)
        goto si3;
    a += HALF_PI;
    if (a >= 0) {
        a -= HALF_PI;
        goto si3;
    }
    a -= HALF_PI;
    goto si1;
}
