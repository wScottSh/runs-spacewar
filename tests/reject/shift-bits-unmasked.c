/* reject: the count bits are w & m, m within 777 */
/* The count field is nine bits; bits above it would change the opcode. */

HOMED shift slot = SHIFT_UNSET;

JDA word f(word a)
{
    slot = I_SAR_BITS(a);
    return xct(slot, a);
}
