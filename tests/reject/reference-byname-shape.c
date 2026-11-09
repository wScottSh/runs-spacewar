/* reject-reference: rewrote 0 of 2 BYNAME uses */
/* The dialect accepts `BYNAME const word`, but the native reference build
 * binds only `BYNAME word p`. Left unbound, b would be a copy read once
 * instead of the caller's word read again at every use. */

JDA word g(word a, BYNAME const word b);

extern word total;

JDA word g(word a, BYNAME const word b)
{
    word s = b;
    s = s + a;
    total = s;
    return total;
}

word total = 0;
