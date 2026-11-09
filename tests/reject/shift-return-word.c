/* reject: widen holds a shift */
/* A function returning a shift builds one; a word is not a shift. */

HOMED shift slot = SHIFT_UNSET;

static inline shift widen(word b)
{
    return b | I_SCL(0);
}

JDA word f(word a)
{
    slot = widen(a);
    return xct(slot, a);
}
