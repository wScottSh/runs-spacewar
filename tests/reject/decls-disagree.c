/* reject: declarations disagree */
/* SYM on the definition but not on the declaration: one of the two would
 * be decoration, so the dialect asks for every declaration to agree. */

JDA word negate(word a);

JDA SYM("neg") word negate(word a)
{
    return -a;
}
