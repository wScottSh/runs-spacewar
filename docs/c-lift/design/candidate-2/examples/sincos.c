/* sincos.c -- source lines 190-254.  Listing 00066-00155.
 * Requires mpy (impmpy.c) for the declaration below.                         */
#include "../pdp1.h"

#define HALF_PI 062210                /* pi/2, binary point right of bit 3   */
#define TWO_PI  0311040

PDP1_JDA word mpy(word a, inl_insn b); /* returns hi word, IO = lo word       */
PDP1_AS(sin) PDP1_JDA word sine(word x);

/* cos has no body of its own: it is sin of (x + pi/2).  The tail call with a
 * `jda` callee is lowered as link forwarding (rule C6): cos's prologue does
 * `dap` into *sin's* link cell, the argument goes into sin's entry word, and
 * control enters sin at its fast entry (AC already holds the argument).      */
PDP1_AS(cos) PDP1_JDA word cosine(word x)
{
    return sine(HALF_PI + x);
}

PDP1_AS(sin) PDP1_JDA word sine(word x)         /* x is sin's entry cell (00074)        */
{
#define C ENTRY(cosine)                  /* cos's entry word is sin's scratch    */
    word a = x;                       /* fast entry follows this load         */
    if (a < 0)
si1:    a += TWO_PI;
    a -= HALF_PI;
    if (a >= 0) goto si2;
    a += HALF_PI;
si3:
    a = ral(a, 2);
    a = mpy(a, 0242763);  x = a;      /* x := k1*arg                          */
    a = mpy(a, x);        C = a;      /* C := x*x                             */
    a = mpy(a, 0756103) + 0121312;
    a = mpy(a, C) + 0532511;
    a = mpy(a, C) + 0144417;
    a = mpy(a, x);
    a = scl(a, 3);        C = a;
    if ((a ^ x) < 0) {                /* sign flipped: overflowed, saturate   */
        word sat = 0377777;
        IO = x;
        if (IO < 0) sat = ~sat;
        return sat;
    }
    return C;                         /* return cell (csx) is emitted here    */

si2:
    a = ~a;
    a += HALF_PI;
    if (a >= 0) goto si3;
    a += HALF_PI;
    if (a < 0) goto si4;
    a -= HALF_PI;
    goto si3;
si4:
    a -= HALF_PI;
    goto si1;
#undef C
}
