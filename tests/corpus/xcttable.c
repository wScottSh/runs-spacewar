/* corpus: entry=launch */
/* A table of one-instruction tunables, executed in place by xct, placed
 * apart from the code at 0300, and a launch routine that uses them: a
 * countdown, a speed scaled down by `speed_shift`, and the speed and x
 * spread across AC:IO by `spread`. */

XCT word countdown(void);
XCT word speed_shift(word v);
XCT dword spread(word hi, register word lo);

extern word timer, speed, low;

JDA dword launch(word v)
{
    word t = countdown();
    timer = t;
    word s = speed_shift(v);
    speed = s;
    register word lo = v;
    dword p = spread(s, lo);
    low = p.lo;
    return (dword){ p.hi, p.lo };
}

word timer = 0;
word speed = 0;
word low = 0;

AT(0300) XCT word countdown(void)
{
    return -015;
}

XCT word speed_shift(word v)
{
    return v >> 3;
}

XCT dword spread(word hi, register word lo)
{
    rcl(hi, lo, 5);
    return (dword){ hi, lo };
}
