/* reject: home is `dzm .`, not `dac .` */
/* A HOMED pointer has one home instruction: a store of a value there
 * cannot also be the store of zero elsewhere. */

HOMED word *p;
word table[2] = { 1, 2 };

JDA word f(word a)
{
    p = table;
    if (a == 0)
        goto zero;
    *home(p) = a;
    return a;
zero:
    *home(p) = 0;
    return a;
}
