/* imp, mpy -- BBN multiply (source lines 260-301).
 * Call: mpy(a, b) with a in AC and b an operand the routine fetches itself
 * (BYNAME: the call is `jda mpy / lac b`). mpy returns 34 bits and two
 * signs in AC:IO; imp returns the low 17 bits and sign in AC. */
#include "spacewar.h"

JDA word imp(word a, BYNAME word b)
{
    dword p = mpy(b, a);            /* operands swapped: b is fetched first */
    p.lo = rir(p.lo, 1);
    rcr(p.hi, p.lo, 18);            /* low half to AC */
    return p.hi;
}

static word mp2 = 0;                /* placed between imp and mpy */

JDA dword mpy(word a, BYNAME word b)
{
    word h = a;
    if (h < 0)
        h = -h;
    register word m;                /* multiplier: |a| into IO */
    rcr(h, m, 18);
    h = b;
    if (h < 0)
        h = -h;
    mp2 = h;                        /* |b| */
    h = 0;
    for (int i = 0; i < 21; i++)    /* int loop: unrolled */
        mus(h, m, mp2);
    mp2 = h;
    if ((b ^ a) < 0) {              /* signs differ: negate the 36-bit product */
        h = -mp2;
        rcr(h, m, 18);
        h = -h;
        rcr(h, m, 18);
        mp2 = h;
    }
    return (dword){ mp2, m };
}
