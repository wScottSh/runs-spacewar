/* reject: must be one operate-group instruction */
/* An add is not in the operate group, so the parts are two instructions. */

word step = 1;

JDA word f(word x)
{
    word a = x;
    register word b;
    a = a + step, b = 0;
    return a;
}
