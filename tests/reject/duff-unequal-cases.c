/* reject: one power of two of words long */
/* The jump into Duff's device scales the case number by a shift, so every
 * case before the last has the same power-of-two length. */

word a = 0;
HOMED word skip;

JDA word f(word x)
{
    skip = x;
    switch ((int)skip) {
    case 0: a = a + 1;
    case 1: ++a;
    case 2: ++a;
    }
    return a;
}
