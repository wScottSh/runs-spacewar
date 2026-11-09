/* reject: changes IO: write xct(w, hi, lo) */
/* xct(w, a) promises IO is left alone; a combined shift moves bits through
 * IO, so it takes the pair form. */

JDA word f(word a)
{
    return xct(I_SCL(2), a);
}
