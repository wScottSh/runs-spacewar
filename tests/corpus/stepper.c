/* corpus: entry=step */
/* A stepper that turns a position word. Each call first turns it by the
 * rotation the previous call left (one place at the start), run where it
 * stands, then sets the next call's rotation from the low three bits of
 * its AC. A pointer held in the `xct` that runs it picks a damping from a
 * table: the first entry, or the second when the turned position is
 * negative. The call returns the damped position halved by a shift run
 * from a constant. */

HOMED insn turn = I_RAL(1);
HOMED const insn *pace;
insn paces[2] = { I_SAR(1), I_SAR(5) };
word position = 0123457;

JDA word step(word x)
{
    word a = position;
    a = xct(turn, a);
    position = a;
    turn = (x & 07) | I_RAL(0);
    pace = paces;
    a = position;
    if (a < 0)
        ++pace;
    a = xct(*home(pace), position);
    return xct(I_SAR(1), a);
}
