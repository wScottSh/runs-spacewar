/* corpus: entry=run */
/* Writes a routine into an area as instruction words, one word for each of
 * the six high bits of a pattern (lio when the bit is 0, dio when it is 1),
 * after a set-flag word and before a tail of fixed words. The area is the
 * word after the call to emit. The routine is data here: nothing runs it.
 * emit steps its return address past that word only after writing the
 * first word; run calls it and returns where the routine ends. */

RESERVE word area[16];
POOL word *out;
word counter = 0;
word saved = 0;

JDA word *emit(word pattern, INLINE word *where);

JDA word *emit(word pattern, INLINE word *where)
{
    register word bits;
    word bit;

    out = where;
    *out++ = I_STF(3);
    ARGS_DONE();
    bits = pattern;
    counter = -6;
next:
    bit = 0;
    rcl(bit, bits, 1);
    if (bit == 0)
        *out++ = I_LIO(&saved);
    else
        *out++ = I_DIO(&saved);
    if (++counter < 0)
        goto next;
    *out++ = I_DAC(&counter);
    *out++ = I_RCL(4);
    *out++ = I_CLF(3);
    *out++ = I_SZF(2);
    *out++ = I_IOH;
    *out++ = I_DPY_NOWAIT;
    return out;
}

JDA word *run(word pattern)
{
    return emit(pattern, area);
}
