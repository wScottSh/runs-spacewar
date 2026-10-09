/* corpus: entry=addchk,subchk */
/* Checked add (a + b) and subtract (b - a) of a word passed by name. The
 * result is in AC; IO holds 0, or the wrapped result when the operation
 * overflowed. Without overflow the call skips the word after b. */

JDA dword subchk(word a, BYNAME word b);
JDA dword addchk(word a, BYNAME word b);
BLOCK dword finish(BYNAME word b);

ENTRY_CELL(addchk) word sum;
ENTRY_CELL(subchk) word result;

JDA dword subchk(word a, BYNAME word b)
{
    sum = -a;
    return finish(b);
}

JDA dword addchk(word a, BYNAME word b)
{
    sum = a;
    return finish(b);
}

BLOCK dword finish(BYNAME word b)
{
    word s = b;
    s = s + sum;
    result = s;
    register word lost = 0;
    s = s ^ sum;
    if (s >= 0)
        goto fine;
    s = b ^ sum;
    if (s < 0)
        goto fine;
    lost = result;
    goto done;
fine:
    skip_return();
done:
    return (dword){ result, lost };
}
