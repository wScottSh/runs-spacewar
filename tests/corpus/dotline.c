/* corpus: entry=dots */
/* Plots a dotted line from the origin with Duff's device: 16 dots, less
 * the number the low three bits of the argument skip. Each dot steps x up
 * and y down by the argument's high bits. With sense switch 2 on, the line
 * is drawn again from where it ended, with x mirrored. Returns the last x. */

word step = 0;
HOMED word dots_skipped;

/* One dot: move the pen by the step and plot. The pen is x in AC and y in
 * IO; only AC adds, so y is exchanged into AC to step it. */
static inline dword dot(word x, register word y)
{
    x = x + step;
    rcl(x, y, 18);
    x = x - step;
    rcl(x, y, 18);
    ioh();
    dpy(x, y, 2);
    return (dword){ x, y };
}

JDA word dots(word arg)
{
    word n;
    dword pen;

    n = arg & 07;
    dots_skipped = n;
    n = arg >> 9;
    step = n;
    pen.hi = 0, pen.lo = 0, clf(2);
    for (;;) {
        switch ((int)dots_skipped) {
        case 0: pen = dot(pen.hi, pen.lo);
        case 1: pen = dot(pen.hi, pen.lo);
        case 2: pen = dot(pen.hi, pen.lo);
        case 3: pen = dot(pen.hi, pen.lo);
        case 4: pen = dot(pen.hi, pen.lo);
        case 5: pen = dot(pen.hi, pen.lo);
        case 6: pen = dot(pen.hi, pen.lo);
        case 7:
            for (int i = 0; i < 9; i++)
                pen = dot(pen.hi, pen.lo);
        }
        if (!sense(2))
            return pen.hi;
        if (flag(2))
            return pen.hi;
        stf(2);
        pen.hi = -pen.hi;
    }
}
