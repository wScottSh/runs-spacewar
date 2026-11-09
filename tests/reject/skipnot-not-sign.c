/* reject: SKIPNOT(c) takes a sign test of AC */
/* Only the sign tests have a second encoding with the i bit flipped. */

JDA word f(word a)
{
    if (SKIPNOT(a == 0))
        return 1;
    return a;
}
