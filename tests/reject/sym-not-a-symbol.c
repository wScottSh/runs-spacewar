/* reject: SYM('a_b') is not a Macro symbol */
/* Macro symbols are lower-case letters and digits; macro1 would read the
 * underscore as an error or as part of an expression. */

JDA SYM("a_b") word f(word a);

JDA SYM("a_b") word f(word a)
{
    return -a;
}
