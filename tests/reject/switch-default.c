/* reject: a jump table has cases 0..n and no default */
/* A jump table has a slot for each value 0..n and none for "anything else". */

JDA word f(word a)
{
    word k = a;
    switch ((int)k) {
    case 0: goto zero;
    default:
        return a;
    }
zero:
    return k;
}
