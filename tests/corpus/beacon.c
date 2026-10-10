/* corpus: entry=beacon */
/* A beacon reads its sensor through the pointer word `sensor` (a JSP
 * routine that returns a pair), keeps the low half's top bits in `level`,
 * and asks inside_band whether level is within x of zero; inside_band
 * returns past the word after its call when it is. The beacon then steps
 * its lamp pointer, held in the instruction that adds the lamp's
 * brightness, and stores the sum through it. A lamp at 0 is lit with -0.
 * It finds the first lamp that is not dark (the last never is) and adds
 * it to `edge`. The beacon jumps to the blink through a pointer held in
 * the jump, set to `steady` or `flash` by sense switch 3; every path ends
 * in `off`, which keeps the routine word of `steady`. */

typedef dword sensor_fn(void) JSP;
typedef word blink_fn(void) BLOCK;

POOL sensor_fn *sensor;
POOL word level;
POOL word seen;
word lamps[4] = { 0, 1, 0, 0400000 };
word edge = 0;
word side = 0777;
word last_blink = 0;
HOMED word *lamp;
HOMED word *lit;
HOMED blink_fn *blink;

JDA SKIPS dword inside_band(word x, BYNAME word lim);
BLOCK SKIPS dword margin(BYNAME word lim);
ENTRY_CELL(inside_band) word mag;

JDA SKIPS dword inside_band(word x, BYNAME word lim)
{
    if (x < 0)
        x = -x;
    mag = x;
    return margin(lim);
}

BLOCK SKIPS dword margin(BYNAME word lim)
{
    word e = lim;
    if (e < 0)
        e = -e;
    edge = e;
    e = mag - edge;
    if (e < 0)
        goto inside;
    {
        register word out = mag;
        return (dword){ e, out };
    }
inside:
    skip_return();
    register word none = 0;
    side = none;
    e = edge - mag;
    return (dword){ e, none };
}

JSP dword read_sensor(void)
{
    word a = level;
    register word b = seen;
    return (dword){ a, b };
}

BLOCK word choose(void);
BLOCK word steady(void);
BLOCK word flash(void);
BLOCK word off(void);

JDA word beacon(word x)
{
    dword d;

    seen = x;
    sensor = read_sensor;
    d = sensor();
    d.lo = rir(d.lo, 4);
    level = d.lo;
    d = inside_band(level, x);
    seen = d.hi;
    lamp = lamps;
    if (sense(1))
        ++lamp;
    word s = seen + *home(lamp);
    *lamp = s;
    if (0 == *lamp)
        *lamp = MINUS_ZERO;
    return choose();
}

BLOCK word choose(void)
{
    lit = lamps;
find:
    if (*home(lit) != 0)
        goto found;
    if (I_LAC(++lit) != I_LAC(lamps + 4))
        goto find;
    for (;;)
        hlt();                      /* the last lamp is never dark */
found:
    edge = edge + *lit;
    if (sense(3))
        goto flashing;
    blink = steady;
    goto go;
flashing:
    blink = flash;
go:
    if (sense(4))
        return off();
    return (*home(blink))();
}

BLOCK word steady(void)
{
    level = level >> 1;
    return off();
}

BLOCK word flash(void)
{
    level = -level;
    return off();
}

BLOCK word off(void)
{
    last_blink = steady | (word)0;
    return level + edge;
}
