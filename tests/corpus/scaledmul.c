/* corpus: entry=scale,square */
/* scale: the low 9 bits of |a| times |k|, k passed by name, signed like
 * a * k; the product comes back in AC:IO. square squares x through scale
 * and keeps the low half in `low`. */

JDA dword scale(word a, BYNAME word k);

word kmag = 0;
word low = 0;

JDA word square(word x)
{
    dword p = scale(x, x);
    low = p.lo;
    return p.hi;
}

JDA dword scale(word a, BYNAME word k)
{
    word h = a;
    if (h < 0)
        h = -h;
    register word m = h;
    h = k;
    if (h < 0)
        h = -h;
    kmag = h;
    h = 0;
    for (int i = 0; i < 011; i++)
        mus(h, m, kmag);
    kmag = h;
    if ((k ^ a) < 0)
        kmag = -kmag;
    return (dword){ kmag, m };
}
