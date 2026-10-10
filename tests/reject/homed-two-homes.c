/* reject: defined twice (a HOMED pointer has one home) */
/* A homed pointer is the address field of one instruction; two homes would
 * be two pointers. */

HOMED const word *p;
word table[2] = { 1, 2 };

JDA word f(word a)
{
    p = table;
    word x = *home(p);
    x = *home(p);
    return x;
}
