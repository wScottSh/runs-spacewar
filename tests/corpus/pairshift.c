/* corpus: entry=pairshift */
/* Builds a 36-bit pair from x by single-register rotates, then walks it with
 * the pair shifts and rotates; the pair after each stage is recorded. */

word stage1 = 0;
word stage2 = 0;

JDA dword pairshift(word x)
{
    word a = x;
    a = rar(a, 4);
    register word lo = a;
    lo = rir(lo, 9);
    lo = ril(lo, 1);
    a = ral(x, 1);
    for (int i = 0; i < 3; i++)
        scl(a, lo, 6);
    stage1 = a;
    scr(a, lo, 35);
    stage2 = a;
    rcr(a, lo, 18);
    scl(a, lo, 2);
    return (dword){ a, lo };
}
