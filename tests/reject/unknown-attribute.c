/* reject: unknown dialect attribute pdp1_inline */
/* A misspelled or invented dialect attribute must not be ignored. */

__attribute__((pdp1_inline)) JDA word f(word a);

JDA word f(word a)
{
    return -a;
}
