/* BBN multiply (source lines 257-301).
 * One factor arrives in AC; the other is passed by name, as the word after
 * the call (`jda mpy / lac b`), and fetched each time it is read.
 * multiply returns the product's 34 bits and two signs in AC:IO;
 * integer_multiply returns its low 17 bits and sign in AC. */

JDA SYM("mpy") dword multiply(word a, BYNAME word b);

JDA SYM("imp") word integer_multiply(word a, BYNAME word b)
{
    dword p = multiply(b, a);       /* b is fetched first; a goes by name */
    p.lo = rir(p.lo, 1);            /* the low half's sign, bit 17, back to bit 0 */
    return p.lo;
}

word partial = 0;                   /* mp2: |b|, then the product's high half */

JDA SYM("mpy") dword multiply(word a, BYNAME word b)
{
    word h = a;
    if (h < 0)
        h = -h;
    register word m = h;            /* |a| is the multiplier, shifted out of IO */
    h = b;
    if (h < 0)
        h = -h;
    partial = h;
    h = 0;
    for (int i = 0; i < 021; i++)   /* 17 multiply steps */
        mus(h, m, partial);
    partial = h;
    if ((b ^ a) < 0) {              /* signs differ: negate the 36-bit product */
        h = -partial;
        rcr(h, m, 18);
        h = -h;
        rcr(h, m, 18);
        partial = h;
    }
    return (dword){ partial, m };
}
