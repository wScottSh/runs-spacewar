/* reject: its value is the address field of an instruction */
/* A homed pointer's home word has its opcode above the address: its value
 * can only go where a dap keeps the address bits. */

HOMED const word *p;
word table[2] = { 1, 2 };
word saved = 0;

JDA word f(word a)
{
    p = table;
    word x = *home(p);
    saved = 1 + p;
    return x;
}
