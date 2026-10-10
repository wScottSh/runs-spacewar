/* reject: defined twice */
/* A HOMED shift is the one word where it runs; running it in two places
 * would make two words of it. */

HOMED shift slot = I_SAR(1);

JDA word f(word a)
{
    a = xct(slot, a);
    return xct(slot, a);
}
