/* BBN multiply (source lines 257-301).
 * One factor arrives in AC; the other is passed by name, as the word after
 * the call (`jda mpy / lac b`), and fetched each time it is read.
 * multiply returns the product's 34 bits and two signs in AC:IO;
 * integer_multiply returns its low 17 bits and sign in AC. */

JDA dword multiply(word a, BYNAME word b);

JDA word integer_multiply(word a, BYNAME word b)  /* imp */
{
    dword product = multiply(b, a); /* b is fetched first; a goes by name */
    product.lo = rir(product.lo, 1);    /* the low half's sign, bit 17, back to bit 0 */
    return product.lo;
}

word partial = 0;                   /* mp2: |b|, then the product's high half */

JDA dword multiply(word a, BYNAME word b)  /* mpy */
{
    word magnitude = a;
    if (magnitude < 0)
        magnitude = -magnitude;
    register word low = magnitude;  /* |a|, the multiplier, shifted out of IO as
                                       the product's low half shifts in */
    magnitude = b;
    if (magnitude < 0)
        magnitude = -magnitude;
    partial = magnitude;
    word high = 0;
    for (int i = 0; i < 021; i++)   /* 17 multiply steps */
        mus(high, low, partial);
    partial = high;
    if ((b ^ a) < 0) {              /* signs differ: negate the 36-bit product */
        high = -partial;
        rcr(high, low, 18);
        high = -high;
        rcr(high, low, 18);
        partial = high;
    }
    return (dword){ partial, low };
}
