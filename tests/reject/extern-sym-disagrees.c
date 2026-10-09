/* reject: declarations disagree */
/* An extern that pins a symbol must agree with the object's definition. */

extern word sum SYM("total");
word sum = 0;

JDA word add(word a)
{
    sum = a;
    return sum;
}
