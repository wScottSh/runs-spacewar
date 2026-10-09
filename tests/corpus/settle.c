/* corpus: entry=settle */
/* Moves a value toward zero in a fixed number of damped steps. Each step
 * subtracts the value scaled by `damping`; `steps` gives the negated count.
 * Both are one-instruction XCT functions. The working words are reserved,
 * not punched, at 0400. */

XCT word damping(word v)
{
    return v >> 2;
}

XCT word steps(void)
{
    return -6;
}

AT(0400) RESERVE word left;
RESERVE word value;

JDA word settle(word x)
{
    value = x;
    word n = steps();
    left = n;
    for (;;) {
        if (++left >= 0)
            return value;
        word d = value;
        d = damping(d);
        d = -d;
        d = d + value;
        value = d;
    }
}
