/* corpus: entry=nibble */
/* Four divide steps by ten on the pair x >> 9 : x << 9, for x >= 0. The
 * partial remainder is left in `rem` and AC, the shifted dividend with the
 * four new quotient bits in `quot` and IO. A negative x skips the divide:
 * the call returns one word further with x in AC and 0 in IO. */

JDA dword nibble(word x);
BLOCK dword finish(word h, register word lo);

extern word ten, rem, quot;

JDA dword nibble(word x)
{
    word h = x;
    if (h < 0)
        goto negative;
    {
        register word lo = 0;
        scr(h, lo, 9);
        for (int i = 0; i < 4; i++)
            dis(h, lo, ten);
        return finish(h, lo);
    }
negative:
    skip_return();
    register word r = 0;
    word m = x;
    return finish(m, r);
}

BLOCK dword finish(word h, register word lo)
{
    rem = h;
    quot = lo;
    return (dword){ h, lo };
}

word ten = 012;
word rem = 0;
word quot = 0;
