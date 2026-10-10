/* reject: a case before the last is `goto label;` or empty */
/* A slot before the last holds one word: the jump to the case's code. */

word seen = 0;

JDA word f(word a)
{
    word k = a;
    switch ((int)k) {
    case 0:
        seen = k;
        goto done;
    case 1:
        return k;
    }
done:
    return seen;
}
