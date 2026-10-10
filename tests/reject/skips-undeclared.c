/* reject: declare it SKIPS exactly when it calls skip_return() */
/* A caller lays out the word a call may skip only for a SKIPS function. */

JDA word f(word a)
{
    if (a < 0)
        return a;
    skip_return();
    return a;
}
