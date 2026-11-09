/* corpus: entry=scan */
/* A ring of eight readings, scanned from where the last scan left off.
 * scan(low) plots each reading in the window [low, low + 0100), at a
 * height that counts the readings found, and stops at the first reading
 * outside the window once it has found any, or after going once round the
 * ring. A scan that finds nothing moves the next scan's start one reading
 * on. Returns the number found. */

word ring[8] = { 0100, 0250, 0177, 0400, 0010, 0130, 0777, 0160 };
HOMED const word *reading = 0;      /* the reading looked at */
const word *resume = ring;          /* where the next scan starts */
insn started = I_LAC(0);            /* `lac` the reading this scan started at */
word low = 0;
word found = 0;

/* How far v is into the window, or -1 when it is outside. */
static inline word window_offset(word v)
{
    v = v - low;
    if (v < 0)
        return -1;
    v = v - 0100;
    if (v >= 0)
        return -1;
    return v + 0100;
}

JDA word scan(word arg)
{
    word v;
    register word y;

    low = arg & 0777;
    found = 0;
    started.addr = resume;
    reading = resume;
next:
    v = window_offset(*home(reading));
    if (v < 0)
        goto outside;
    v = v << 8;
    y = found;
    dpy(v, y, 1);
    ++found;
step:
    if (I_LAC(++reading) == I_LAC(ring + 8))
        reading = ring;
    if (I_LAC(reading) == started)
        return found;
    goto next;
outside:
    if (found != 0)
        return found;
    ++resume;
    if (resume == ring + 8)
        resume = ring;
    goto step;
}
