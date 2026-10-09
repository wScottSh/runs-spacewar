/* corpus: entry=popcnt */
/* Number of one bits in an 18-bit word: rotate each bit out of IO into AC. */

extern word left, ones;

JDA word popcnt(word x)
{
    left = -022;                    /* isp reaches 0 after 18 passes */
    ones = 0;
    register word bits = x;
    for (;;) {
        if (++left >= 0)
            return ones;
        word b = 0;
        rcl(b, bits, 1);            /* top bit of IO into AC */
        if (b == 0)
            continue;
        ++ones;
    }
}

word left = 0;
word ones = 0;
