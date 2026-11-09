/* reject: ARGS_DONE() must follow every read of a word after the call */
/* Stepping the return address before reading the inline word would read
 * the word after it. */

word copy = 0;

JDA word f(word a, INLINE word n)
{
    ARGS_DONE();
    word x = n;
    copy = x;
    return a;
}
