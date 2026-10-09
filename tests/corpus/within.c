/* corpus: entry=within */
/* Is x inside the band -lim..lim, lim passed by name? The distance from |x|
 * to the edge comes back in AC. Outside the band IO holds x's magnitude and
 * the call returns to the word after lim; inside, IO is 0, `side` is cleared
 * and the call skips that word. */

JDA dword within(word x, BYNAME word lim);
BLOCK dword margin(BYNAME word lim);

ENTRY_CELL(within) word mag;        /* within's entry word: x, then |x| */
extern word edge, side;

JDA dword within(word x, BYNAME word lim)
{
    if (x < 0)
        x = -x;
    mag = x;                        /* the same cell: no code */
    return margin(lim);
}

BLOCK dword margin(BYNAME word lim)
{
    word e = lim;
    if (e < 0)
        e = -e;
    edge = e;
    e = mag - edge;
    if (e < 0)
        goto inside;
    {
        register word out = mag;
        return (dword){ e, out };
    }
inside:
    skip_return();
    register word none = 0;
    side = none;
    e = edge - mag;
    return (dword){ e, none };
}

word edge = 0;
word side = 0777;
