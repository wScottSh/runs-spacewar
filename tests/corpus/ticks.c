/* corpus: entry=ticks */
/* Plots a row of tick marks right to left from x = -arg, one tick per two
 * words of code: Duff's device enters the row at the tick the argument's
 * low three bits name, so 8 to 1 ticks are drawn. With sense switch 5 on
 * nothing is drawn. With sense switch 1 on one dim tick is drawn, flag 1
 * is set and the x is mirrored. Returns the x after the last tick. */

word spacing = 0400;
HOMED word first_tick;

JDA word ticks(word arg)
{
    word x;
    register word y;

    first_tick = arg & 07;
    x = arg;
    x = -x, y = 0;
    if (sense(5))
        return x;
    if (sense(1))
        goto dim;
    switch ((int)first_tick) {
    case 0: dpy(x, y, 3); x = x + spacing;
    case 1: dpy(x, y, 3); x = x + spacing;
    case 2: dpy(x, y, 3); x = x + spacing;
    case 3: dpy(x, y, 3); x = x + spacing;
    case 4: dpy(x, y, 3); x = x + spacing;
    case 5: dpy(x, y, 3); x = x + spacing;
    case 6: dpy(x, y, 3); x = x + spacing;
    case 7: dpy(x, y, 3); x = x + spacing;
    }
    ioh();
    return x;
dim:
    dpy(x, y, 7);
    x = -x, stf(1);
    return x;
}
