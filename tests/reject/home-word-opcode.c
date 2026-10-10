/* reject: home is `lio .`, not `lac` */

word table[2] = { 1, 2 };
HOMED const word *p = 0;

JDA word f(word x)
{
    register word v;
    p = table;
    v = *home(p);
    if (I_LAC(++p) == I_LAC(table + 2))
        return x;
    return x;
}
