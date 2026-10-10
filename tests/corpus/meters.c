/* corpus: entry=sweep */
/* Three gauges kept in parallel tables: a reading, a countdown and a
 * status word. sweep(v) walks them with cursors, one held in the
 * instruction that loads the reading and two in pool words. Each gauge's
 * reading grows by v. Its countdown ticks, and when it runs out the
 * countdown restarts at -3 and the status word gets the address of `alarm`
 * with the flag bit set; a quiet gauge's status loses its flag, and with
 * v = 0 is cleared. Returns the last reading. */

#define FLAGGED ((word)0400000)

word readings[3] = { 0, 0100, 07000 };
word countdowns[3] = { -3, -1, -07 };
word status[3] = { 0, 0, 0 };
HOMED word *reading;
POOL word *countdown;
POOL word *state;
POOL word gauges_left;
POOL word last;

JSP void alarm(void)
{
}

JDA word sweep(word v)
{
    word r;

    reading = readings;
    countdown = countdowns;
    state = status;
    gauges_left = -3;
next:
    r = *home(reading) + v;
    *reading = r;
    last = r;
    if (++*countdown < 0)
        goto quiet;
    *countdown = -3;
    *state = alarm | FLAGGED;
    goto step;
quiet:
    *state = *state & 07777;
    if (v == 0)
        *state = 0;
step:
    ++reading;
    ++countdown;
    ++state;
    if (++gauges_left < 0)
        goto next;
    return last;
}
