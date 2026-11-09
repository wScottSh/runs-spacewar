/* reject: xct runs a shift */
/* The reference build gives meaning to running a shift-group word only; a
 * skip run by xct would skip a word of the code around it. */

JDA word f(word a)
{
    return xct(I_SZF(1), a);
}
