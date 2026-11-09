/* reject: has no home */
/* A HOMED pointer defined here lives in one instruction here. One that no
 * *home(p) places has no word to hold it. */

HOMED word *p;
word table[2] = { 1, 2 };

JDA word f(word a)
{
    p = table;
    return *p + a;
}
