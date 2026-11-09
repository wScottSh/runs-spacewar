/* corpus: entry=times inputs=0..0177 */
/* n * (n - 1) by repeated addition; the counter runs from -n up to 0. */

extern word count, total;

JDA word times(word n)
{
    count = -n;
    total = 0;
    for (;;) {
        if (++count >= 0)
            return total;
        total = total + n;
        if (total >= 0)
            continue;
        total = 0400;               /* overflowed into the sign: restart at 0400 */
    }
}

word count = 0;
word total = 0;
