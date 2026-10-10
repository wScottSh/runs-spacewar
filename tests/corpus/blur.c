/* corpus: entry=blur */
/* Blurs a point held across AC:IO. IO is doubled twice by a shift of IO
 * alone, the pair moves one place left by a shift run from a constant,
 * and then right by as many places as AC has bits set among 0700, by a
 * shift built at run time and run where it stands; its first run would
 * halt, so every call builds it before reaching it. `last` records the
 * address of blur with a flag bit, and the call's sign in a second one.
 * Returns the blurred AC:IO. */

#define SEEN ((word)0200000)
#define SEEN_NEGATIVE ((word)0600000)

HOMED insn smear = I_HLT;
word last = 0;

JDA dword blur(word a, register word lo)
{
    dword p;

    smear = (a & 0700) | I_SCR(0);
    last = blur | SEEN;
    if (a < 0)
        last = blur | SEEN_NEGATIVE;
    lo = lo << 2;
    p = xct(I_SCL(1), a, lo);
    p = xct(smear, p.hi, p.lo);
    return (dword){ p.hi, p.lo };
}
