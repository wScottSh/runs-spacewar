/* reject: initialize it with the instruction it holds first */
/* A HOMED shift's word is laid out in the code, so it needs the word the
 * machine finds there before the program stores another. */

HOMED shift slot;

JDA word f(word a)
{
    return xct(slot, a);
}
