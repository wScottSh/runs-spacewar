/* corpus: entry=cmpall */
/* Every comparison with 0, once as a one-word body (skip on the negation)
 * and once as a longer body (skip over a jump). Each counter records how
 * often its test held; the result packs the longer-body outcomes as bits. */

extern word lt, ge, eq, ne, le, gt, bits;

JDA word cmpall(word x)
{
    if (x < 0) ++lt;
    if (x >= 0) ++ge;
    if (x == 0) ++eq;
    if (x != 0) ++ne;
    if (x <= 0) ++le;
    if (x > 0) ++gt;
    bits = 0;
    if (x < 0) bits = bits + 01;
    if (x >= 0) bits = bits + 02;
    if (x == 0) bits = bits + 04;
    if (x != 0) bits = bits + 010;
    if (x <= 0) bits = bits + 020;
    if (x > 0) bits = bits + 040;
    return bits;
}

word lt = 0;
word ge = 0;
word eq = 0;
word ne = 0;
word le = 0;
word gt = 0;
word bits = 0;
