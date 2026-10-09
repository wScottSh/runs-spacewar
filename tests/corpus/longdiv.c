/* corpus: entry=udiv,div1 mirrors=dvd */
/* Long division of the 36-bit AC:IO by a divisor passed by name, in divide
 * steps. The quotient comes back in AC, the remainder's magnitude in IO,
 * and the call skips the word after the divisor. When the quotient cannot
 * fit it returns to that word with |divisor| in AC. div1 divides x:0. */

JDA dword udiv(word hi, register word lo, BYNAME word d);
JDA dword div1(word x, BYNAME word d);
BLOCK dword steps(register word lo, BYNAME word d);

ENTRY_CELL(udiv) word high;
ENTRY_CELL(div1) word dmag;

JDA dword div1(word x, BYNAME word d)
{
    high = x;
    register word lo = 0;
    return steps(lo, d);
}

JDA dword udiv(word hi, register word lo, BYNAME word d)
{
    high = hi;
    return steps(lo, d);
}

BLOCK dword steps(register word lo, BYNAME word d)
{
    word h = d;
    if (h < 0)
        h = -h;
    dmag = h;
    h = high;
    if (h < 0) {
        h = -h;
        rcr(h, lo, 18);
        h = -h;
        rcr(h, lo, 18);
    }
    h = h - dmag;
    if (h >= 0)
        goto too_big;
    for (int i = 0; i < 022; i++)
        dis(h, lo, dmag);
    h = h + dmag;
    dmag = lo;
    lo = h;
    skip_return();
too_big:
    h = dmag;
    return (dword){ h, lo };
}
