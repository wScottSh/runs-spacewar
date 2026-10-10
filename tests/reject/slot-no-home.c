/* reject: has no home */
/* A HOMED shift is laid out where it runs. One that never runs has no
 * place in the code, and its stores would name nothing. */

HOMED shift slot = SHIFT_UNSET;

JDA word f(word a)
{
    slot = I_SAR(1);
    return a;
}
