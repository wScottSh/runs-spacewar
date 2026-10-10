/* reject: declarations disagree */
/* An extern declaration must agree with the object's definition: here it
 * says the word is a pool word, while the definition places it. */

extern POOL word sum;
word sum = 0;

JDA word add(word a)
{
    sum = a;
    return sum;
}
