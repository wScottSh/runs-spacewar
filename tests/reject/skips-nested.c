/* reject: a SKIPS function cannot call the SKIPS function */
/* inner's skip lands on the word after its call, inside outer; outer's own
 * skip lands on its caller. The native reference keeps one skip count per
 * call chain, so it would add inner's skip to outer's return. */

JDA SKIPS word inner(word x);

JDA SKIPS word outer(word x)
{
    word y = inner(x);
    if (y < 0)
        skip_return();
    return y;
}

JDA SKIPS word inner(word x)
{
    if (x < 0)
        skip_return();
    return x;
}
