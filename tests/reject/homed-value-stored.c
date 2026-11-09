/* reject: its value is the address field of an instruction */
/* p + 1 for a HOMED p adds to p's home instruction: only its address
 * field means p + 1, so only a dap may store it. */

HOMED word *p;
POOL word *q;
word table[2] = { 1, 2 };

JDA word f(word a)
{
    p = table;
    q = 1 + p;
    return *home(p) + a;
}
