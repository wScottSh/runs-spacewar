/* reject: home(p) names a HOMED pointer p */

POOL word *p;
word table[2] = { 1, 2 };

JDA word f(word a)
{
    p = table;
    *home(p) = a;
    return a;
}
