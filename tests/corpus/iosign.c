/* corpus: entry=iosign */
/* Tallies the sign of the word arriving in IO, and folds x toward it: x is
 * negated when IO is negative, and halved otherwise. */

JDA word iosign(word x, register word y);

extern word neg, pos, last;

JDA word iosign(word x, register word y)
{
    if (y < 0)
        ++neg;
    if (y >= 0)
        ++pos;
    if (y < 0) {
        x = -x;
        last = x;
    }
    if (y >= 0) {
        x = x >> 1;
        last = x;
    }
    return x;
}

word neg = 0;
word pos = 0;
word last = 0;
