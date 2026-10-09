/* corpus: entry=absdif */
/* |x - base|, halved when positive; remembers the difference in diff. */

extern word base, diff;

JDA word absdif(word x)
{
    base = 0712345 ^ base;          /* the base alternates between two values */
    word d = x - base;
    diff = d;
    if (d < 0) {
        d = -d;
        diff = d;
        return d;
    }
    if (d > 0)
        d = d >> 1;
    d = d + 0123456;
    return d;
}

word base = 0123;
word diff = 0;
