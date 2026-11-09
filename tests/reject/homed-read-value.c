/* reject: its value is the address field of an instruction */
/* Reading a homed pointer as a word would load its home instruction. */

HOMED const word *p;
word table[2] = { 1, 2 };
word saved = 0;

JDA word f(word a)
{
    p = table;
    word x = *home(p);
    saved = p;
    return x;
}
