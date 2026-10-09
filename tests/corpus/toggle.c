/* corpus: entry=toggle */
/* Alternates between two phases from call to call. `current` holds the
 * phase to run next; it starts empty and is set to `even`. Each phase
 * stores its result in `last` and points `current` at the other phase.
 * The call reads the typewriter first, which leaves IO undefined. 0 skips
 * the phases. */

typedef word phase(word v) BLOCK;

RESERVE phase *current;
extern word last;

BLOCK word even(word v);
BLOCK word odd(word v);
BLOCK word finish(void);

JDA word toggle(word x)
{
    tyi();
    if (current == 0)
        current = even;
    word v = x;
    if (v == 0) {
        last = v;
        return finish();
    }
    return current(v);
}

BLOCK word even(word v)
{
    v = v + 1;
    last = v;
    current = odd;
    return finish();
}

BLOCK word odd(word v)
{
    v = -v;
    last = v;
    current = even;
    return finish();
}

BLOCK word finish(void)
{
    word v = last;
    return v;
}

word last = 0;
