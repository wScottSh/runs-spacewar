/* reject-reference: rewrote 0 of 1 ENTRY_CELL uses */
/* The dialect accepts a SYM between ENTRY_CELL and the type, but the native
 * reference build binds only `ENTRY_CELL(f) word x;`. Left unbound, `seen`
 * would be a separate word instead of g's entry word. */

JDA word g(word a);

ENTRY_CELL(g) SYM("sen") word seen;

JDA word g(word a)
{
    a = a + 1;
    return seen;
}
