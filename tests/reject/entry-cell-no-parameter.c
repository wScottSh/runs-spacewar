/* reject: ENTRY_CELL names a JDA function with an AC parameter */
/* g's entry word is filled from AC by the call, but g names no parameter
 * there, so the reference build has no value to put in the alias. */

JDA word g(void);

ENTRY_CELL(g) word seen;

JDA word g(void)
{
    return seen;
}
