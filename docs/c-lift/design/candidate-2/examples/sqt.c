/* sqt.c -- source lines 309-343, integer square root.  Listing 00246-00305. */
#include "../pdp1.h"

extern word sq1, sq2;                 /* defined in-stream after the routine */

PDP1_JDA word sqt(word x)             /* x IS the entry cell (00246); below it
                                         doubles as the running remainder     */
{
    sq1 = -023;                       /* iteration count, counts up to 0      */
    sq2 = 0;                          /* root                                 */
    IO = x;                           /* radicand rides in IO                 */
    x = 0;                            /* remainder                            */
sq3:
    if (++sq1 >= 0)
        return sq2;
    sq2 = sal(sq2, 1);
    word r = rcl(x, 2);               /* two radicand bits enter the remainder */
    if (r == 0) goto sq3;
    x = r;
    r = sal(sq2, 1) + 1 - x;          /* 2*root+1 - remainder                  */
    if (r > 0) goto sq3;              /* cannot subtract                       */
    if (r < 0) r = -r;                /* r <= 0 here: remainder - (2*root+1)   */
    x = r;
    sq2++;
    goto sq3;
}

word sq1 = 0, sq2 = 0;                /* 00304, 00305                          */
