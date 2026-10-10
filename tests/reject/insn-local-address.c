/* reject: has no address: it is not a word in memory */
/* An AC local has no address for an instruction to name. */

word code = 0;

JDA word f(word a)
{
    word x = a;
    code = I_LAC(&x);
    return x;
}
