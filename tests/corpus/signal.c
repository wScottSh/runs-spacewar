/* corpus: entry=signal */
/* Four lamps in a table after the code. Each entry is the address of a
 * lamp routine with the lamp's colour in the two bits above the address
 * field; the sign bit marks a warm colour. signal(v) refills the table,
 * picks the entry v's low two bits name through a cursor held in the
 * instruction that loads it, moves the entry into IO to see whether the
 * colour is warm, and calls the lamp through the entry's address. A lamp
 * counts its flashes and shows the count and the test word on the console
 * lights. With test word switch 040 set, the lamp after the picked one
 * flashes too. Returns the flashes so far, plus 1 for each warm pick. */

#define LAMPS 4
#define BLUE ((word)0200000)        /* colours: the sign bit is warm */
#define AMBER ((word)0400000)
#define RED ((word)0600000)

typedef void lamp(void) JSP;

extern word lamps[LAMPS + 1];
POOL word chosen;
POOL word flashes;
POOL word warm;
HOMED word *picked;
HOMED word *after;

JSP void red(void)
{
    register word switches = SWAP(lat());
    ++flashes;
    word f = flashes;
    halt(f, switches);
}

JSP void green(void)
{
    word f = flashes;
    f = f + 2;
    flashes = f;
}

JDA word signal(word v)
{
    lamps[0] = red | RED;
    lamps[1] = green;
    lamps[2] = red | BLUE;
    lamps[3] = green | AMBER;
    lamps[4] = green;
    chosen = v & 3;
    word *at = lamps;
    at = at + chosen;
    picked = at;
    after = 1 + picked;
    word entry = *home(picked);
    register word colour = SWAP(entry);
    if (colour < 0)
        ++warm;
    ((lamp *)*picked)();
    if ((lat() & 040) == 0)
        goto counted;
    ((lamp *)*home(after))();
counted:
    return flashes + warm;
}

CONSTANTS();
VARIABLES();
RESERVE word lamps[LAMPS + 1];
