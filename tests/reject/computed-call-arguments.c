/* reject: a computed call takes no arguments */
/* The call is `jsp .` patched with the address: there is nowhere for an
 * argument but the registers, and the function type says which. */

typedef void step(register word io) JSP;
word table[1] = { 0 };

JDA word f(word a)
{
    register word io = a;
    ((step *)table[0])(io);
    return a;
}
