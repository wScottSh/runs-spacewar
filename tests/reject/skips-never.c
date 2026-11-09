/* reject: declare it SKIPS exactly when it calls skip_return() */
/* SKIPS on a function that never skips would lay out a word its callers never pass. */

JDA SKIPS word f(word a)
{
    return a;
}
