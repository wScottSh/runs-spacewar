/* corpus: entry=poly,polyhalf mirrors=sin */
/* Horner evaluation of C0 + u (C1 + u C2) on fractions after folding u into
 * [0, 1/2). poly evaluates at u, polyhalf at u + 1/4; both return through
 * the evaluation block's exit. A negative value comes back as 0. */

#define QUARTER 0100000
#define HALF    0200000
#define C2      -0123456
#define C1      0234567
#define C0      012345

JDA dword fmul(word a, BYNAME word b);
JDA word polyhalf(word u);
JDA word poly(word u);
BLOCK word horner(word u);

ENTRY_CELL(poly) word folded;
ENTRY_CELL(polyhalf) word value;

word fm = 0;

JDA dword fmul(word a, BYNAME word b)
{
    word h = b;
    if (h < 0)
        h = -h;
    fm = h;
    h = a;
    if (h < 0)
        h = -h;
    register word m = h;
    h = 0;
    for (int i = 0; i < 021; i++)
        mus(h, m, fm);
    fm = h;
    if ((b ^ a) < 0)
        fm = -fm;
    return (dword){ fm, m };
}

JDA word polyhalf(word u)
{
    folded = QUARTER + u;
    return horner(folded);
}

JDA word poly(word u)
{
    return horner(u);
}

BLOCK word horner(word u)
{
    if (u < 0)
negate: u = -u;
    u -= HALF;
    if (u >= 0)
        goto too_big;
    u += HALF;
evaluate:
    folded = u;
    u = fmul(u, C2).hi + C1;
    u = fmul(u, folded).hi + C0;
    value = u;
    {
        register word sign = value;
        if (sign < 0)
            return 0;
    }
    return value;
too_big:
    u = -u;
    if (u >= 0)
        goto evaluate;
    goto negate;
}
