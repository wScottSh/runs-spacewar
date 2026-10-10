/* reject: has no exit to share */
/* steer goes on to one of two BLOCKs, so no single exit cell is its own:
 * a JDA function that returns only through steer has nowhere to patch. */

word result = 0;

BLOCK word left(word v)
{
    result = v;
    return v;
}

BLOCK word right(word v)
{
    v = -v;
    return v;
}

BLOCK word steer(word v)
{
    if (v < 0)
        return left(v);
    return right(v);
}

JDA word f(word a)
{
    word v = a;
    return steer(v);
}
