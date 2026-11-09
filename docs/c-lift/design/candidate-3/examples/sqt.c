/* sqt -- integer square root (source lines 309-343).
 * Input in AC, binary point right of bit 17; answer in AC, binary point
 * between bits 8 and 9. Largest input 0177777.
 * The argument's entry word doubles as the running remainder. */
#include "spacewar.h"

extern word sq1, sq2;               /* defined (placed) after the routine */

JDA word sqt(word r)                /* r: the entry word -- input, then remainder */
{
    sq1 = -023;                     /* 19 iterations; isp counts up to 0 */
    sq2 = 0;                        /* root so far */
    register word lo = r;           /* low half of the 36-bit shift register */
    r = 0;
    for (;;) {
        if (++sq1 >= 0)
            return sq2;
        sq2 = sq2 << 1;
        word a = r;
        rcl(a, lo, 2);              /* bring in the next two bits */
        if (a == 0)
            continue;
        r = a;
        a = (sq2 << 1) + 1 - r;     /* trial divisor minus remainder */
        if (a > 0)
            continue;               /* trial too big: root bit is 0 */
        if (a < 0)
            a = -a;
        r = a;
        ++sq2;                      /* root bit is 1 */
    }
}

word sq1 = 0;                       /* initialized file-scope: placed here */
word sq2 = 0;
