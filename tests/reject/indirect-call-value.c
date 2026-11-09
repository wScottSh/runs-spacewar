/* reject: a call through next is a jump */
/* Only a tail call through a pointer is implemented: it is `jmp i next`. */

typedef word step(word v) BLOCK;

RESERVE step *next;

JDA word use(word x)
{
    word r = next(x);
    r = r + x;
    return r;
}
