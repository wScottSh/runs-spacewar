/* corpus: entry=sample */
/* A console program that reads its input through a reader pointer. The
 * tape starts it at `power_on`, which picks the test word switches as the
 * reader and halts, showing the switches. sample(v) picks the switches
 * when v is negative and a fixed pattern otherwise, reads through the
 * pointer (a JSP call that leaves the value in IO) and returns the value
 * with its halves swapped. */

typedef io_word reader(void) JSP;

POOL reader *input;

JSP io_word from_switches(void)
{
    register word io = SWAP(lat());
    return io;
}

JSP io_word from_pattern(void)
{
    register word io = 0252525;
    return io;
}

START BLOCK void power_on(void)
{
again:
    input = from_switches;
    register word shown = input();
    halt(0, shown);
    goto again;
}

JDA word sample(word v)
{
    if (v < 0)
        input = from_switches;
    else
        input = from_pattern;
    register word got = input();
    got = rir(got, 9);
    word out = SWAP(got);
    return out;
}
