/* reject: AC local a was clobbered before this use */
/* `idx i p` leaves the new word in AC, so a value held in AC is gone. */

word table[2] = { 1, 2 };
POOL word *p;

JDA word f(word x)
{
    p = table;
    word a = x;
    ++*p;
    return a;
}
