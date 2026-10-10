/* corpus: entry=sparkle */
/* Scatters a point held across AC:IO. The low nine bits of the call's AC
 * choose a combined left shift, built as an instruction at run time and
 * run where it stands; its first run would halt, so every call builds it
 * before reaching it. A pointer held in the `xct` that runs it picks one
 * of two combined right shifts, the gentler one unless AC is negative.
 * Before both, AC is quartered by a shift run from a constant, and AC and
 * IO are spread apart. IO holds its value across the call that builds the
 * shift. Returns the scattered AC:IO. */

HOMED insn widen = I_HLT;
HOMED const insn *damp;
insn damps[2] = { I_SCR(1), I_SCR(4) };

/* A combined left shift by as many places as b has bits set in its low nine. */
static inline insn left_shift(word b)
{
    return (b & 0777) | I_SCL(0);
}

JDA dword sparkle(word bits, register word lo)
{
    dword p;

    damp = damps;
    widen = left_shift(bits);
    if (bits < 0)
        ++damp;
    p.hi = xct(I_SAR(2), bits);
    scr(p.hi, lo, 9);
    lo = lo >> 3;
    p = xct(*home(damp), p.hi, lo);
    p = xct(widen, p.hi, p.lo);
    return (dword){ p.hi, p.lo };
}
