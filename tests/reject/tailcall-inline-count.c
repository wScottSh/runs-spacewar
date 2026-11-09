/* reject: takes 1 inline word(s) but tail-calls finish, which returns past 0 */
/* start's caller puts b's word after the call. finish knows nothing of it
 * and would return onto that word, executing it as an instruction. */

JDA word start(word a, BYNAME word b);
BLOCK word finish(word a);

JDA word start(word a, BYNAME word b)
{
    word s = b;
    return finish(s);
}

BLOCK word finish(word a)
{
    return -a;
}
