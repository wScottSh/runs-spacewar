/* corpus: entry=route */
/* Routes x through a pointer word: a negative x to `negate`, any other
 * to `halve`, and 0 straight to `finish`. route stores the chosen
 * function's address in `next`, leaves sequence break mode, and jumps
 * through `next`. Every path returns through finish. */

typedef word step(word v) BLOCK;

RESERVE step *next;
extern word result;

BLOCK word negate(word v);
BLOCK word halve(word v);
BLOCK word finish(word v);

JDA word route(word x)
{
    word a = x;
    if (a == 0)
        return finish(a);
    if (a < 0)
        goto negative;
    next = halve;
    goto go;
negative:
    next = negate;
go:
    lsm();
    word v = x;
    return next(v);
}

BLOCK word negate(word v)
{
    v = -v;
    return finish(v);
}

BLOCK word halve(word v)
{
    v = v >> 1;
    return finish(v);
}

BLOCK word finish(word v)
{
    result = v;
    return v;
}

word result = 0;
