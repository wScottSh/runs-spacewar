/* BBN integer square root (source lines 309-343).
 * Input in AC, binary point right of bit 17; answer in AC, binary point
 * between bits 8 and 9. Largest input 0177777.
 * The argument's entry word doubles as the running remainder. */

extern word root_passes_left, partial_root;     /* placed after the routine */

JDA word square_root(word remainder)            /* sqt: the entry word, the input, then the remainder */
{
    root_passes_left = -023;                    /* isp counts up to 0: 022 (18) passes, 2 bits each */
    partial_root = 0;
    register word input_bits = remainder;       /* the low half of the 36-bit AC:IO shift register */
    remainder = 0;
    for (;;) {
        if (++root_passes_left >= 0)
            return partial_root;
        partial_root = partial_root << 1;
        word next_remainder = remainder;
        rcl(next_remainder, input_bits, 2);     /* bring in the next two bits */
        if (next_remainder == 0)
            continue;
        remainder = next_remainder;
        next_remainder = (partial_root << 1) + 1 - remainder;  /* trial divisor minus remainder */
        if (next_remainder > 0)
            continue;                           /* trial too big: root bit is 0 */
        if (next_remainder < 0)
            next_remainder = -next_remainder;
        remainder = next_remainder;
        ++partial_root;                         /* root bit is 1 */
    }
}

word root_passes_left = 0;                      /* sq1 */
word partial_root = 0;                          /* sq2: the root so far */
