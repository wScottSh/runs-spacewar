/* reject: defined twice */
/* A HOMED insn is the one word where it runs; running it in two places
 * would make two words of it. */

HOMED insn shift = I_SAR(1);

JDA word f(word a)
{
    a = xct(shift, a);
    return xct(shift, a);
}
