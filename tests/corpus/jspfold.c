/* corpus: entry=parity */
/* fold, entered by jsp with a word in IO, returns the exclusive or of the
 * word's two 9-bit halves. fold_again only forwards to fold, so fold
 * returns straight to fold_again's caller. parity folds x both ways and
 * keeps the first result. */

JSP word fold(register word bits);
JSP word fold_again(register word bits);

extern word first, half;

JSP word fold(register word bits)
{
    word a = 0;
    rcl(a, bits, 9);
    half = a;
    a = 0;
    rcl(a, bits, 9);
    a = a ^ half;
    return a;
}

JSP word fold_again(register word bits)
{
    return fold(bits);
}

JDA word parity(word x)
{
    register word b = x;
    word f = fold(b);
    first = f;
    register word c = x;
    word g = fold_again(c);
    g = g + first;
    return g;
}

word first = 0;
word half = 0;
