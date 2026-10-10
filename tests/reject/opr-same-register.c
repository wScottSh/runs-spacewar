/* reject: both write AC */
/* cla then cma is -0 and cma then cla is 0: one operate word cannot say which. */

JDA word f(word x)
{
    word a = x;
    a = 0, a = -a;
    return a;
}
