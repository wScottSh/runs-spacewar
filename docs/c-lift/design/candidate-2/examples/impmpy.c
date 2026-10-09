/* impmpy.c -- source lines 257-301.  Listing 00156-00245.
 * Calling sequence:  lac A / jda mpy / lac B   ==   mpy(A, B)
 * The second argument is one inline instruction word after the call.        */
#include "../pdp1.h"

PDP1_JDA word mpy(word a, inl_insn b);          /* returns hi, IO = lo       */
PDP1_JDA word imp(word a, inl_insn b);          /* returns low 17 bits + sign */

PDP1_JDA word imp(word a, inl_insn b)           /* a is the entry cell 00156 */
{
    mpy(b, a);              /* b: first read -> link cell `xct` placed here;
                               call site supplies `lac imp` as mpy's inline arg */
    skip_inline(1);         /* idx im1                                       */
    IO = rir(IO, 1);
    return rcr(ANY(), 18);  /* rcr 9s ; rcr 9s : swap AC and IO              */
}

static word mp2 = 0;                            /* 00170, in-stream           */

PDP1_JDA word mpy(word a, inl_insn b)           /* entry cell 00171           */
{
    word m = a;
    if (m < 0) m = ~m;
    (void)rcr(m, 18);       /* IO := |a|                                      */
    word n = b;             /* mp1: link cell `xct` placed here (first read)  */
    if (n < 0) n = ~n;
    mp2 = n;                /* |b|                                            */
    word acc = 0;
    PDP1_UNROLL
    for (int i = 0; i < 017; i++)
        acc = mus(acc, mp2);
    mp2 = acc;
    if ((b ^ a) >= 0) goto mp3;                 /* second read of b: xct mp1 */
    {
        word p = mp2;                           /* negate the 34-bit product  */
        p = ~p;
        p = rcr(p, 18);
        p = ~p;
        p = rcr(p, 18);
        mp2 = p;
    }
mp3:
    skip_inline(1);
    return mp2;
}
