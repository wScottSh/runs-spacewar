/* corpus: entry=pass */
/* A turnstile that admits on a ticket or on its operator's buttons. pass(v)
 * stores the ticket v and picks the sensor: the buttons (the control
 * boxes, none pressed when none are attached) for a negative ticket, else
 * the ticket reader. It reads the sensor through a pointer, a JSP routine
 * that leaves its reading in IO. A negative reading refuses; otherwise the
 * count cursor steps to the next of four counters and that counter counts
 * the visitor. Returns the counter's new value, or -1 when refused. */

typedef io_word sensor_routine(void) JSP;

extern HOMED word *count;           /* its home is in admit, below */

POOL sensor_routine *sensor;
word ticket = 0;
word counters[4] = { 0, 0, 0, 0 };
word next_counter = 0;

JSP io_word read_ticket(void)
{
    register word t = ticket;
    t = rir(t, 1);
    return t;
}

JSP io_word read_buttons(void)
{
    register word held = 0;
    held = control_boxes();
    return held;
}

JDA word pass(word v)
{
    ticket = v;
    if (v < 0)
        sensor = read_buttons;
    else
        sensor = read_ticket;
    register word reading = sensor();
    if (reading < 0) {
        word no = -1;
        return no;
    }
    word *at = counters;
    at = at + next_counter;
    count = at;
    word n = 1 + next_counter;
    next_counter = n & 3;
    word c = *home(count);
    c = c + 1;
    *count = c;
    return c;
}

word *count;                    /* HOMED by the declaration above */
