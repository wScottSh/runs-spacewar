/* reject: defined twice */
/* A static inline function's PLACEd words are laid out in its copy; two
 * calls would lay the same words out twice. */

word count = 0;

static inline void tick(void)
{
    ++count;
    return;
    PLACE(count);
}

JDA word f(word x)
{
    tick();
    tick();
    return x;
}
