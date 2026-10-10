/* reject: slot holds a shift */
/* A shift slot is executed, so only a shift is stored there; a word with
 * the count bits ORed in is built by I_SCL_BITS instead. */

HOMED shift slot = SHIFT_UNSET;

JDA word f(word a)
{
    slot = (a & 0777) | I_SCL(0);
    return xct(slot, a);
}
