/* corpus: entry=rotmix */
/* Mixes x through every single-register and pair rotate and shift. */

word seen = 0;

JDA dword rotmix(word x)
{
    word a = x;
    a = ral(a, 5);
    a = rar(a, 13);
    register word r = a;
    r = ril(r, 7);
    r = rir(r, 2);
    a = x;
    scl(a, r, 11);
    seen = a;
    scr(a, r, 20);
    rcr(a, r, 3);
    return (dword){ a, r };
}
