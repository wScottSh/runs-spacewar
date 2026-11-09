/* reject: the flags must lie above the address field */
/* f | c is f's address with flags set above it; a c with address bits
 * would change the address, not flag it. */

JSP void handler(void)
{
}

word mark = 0;

JDA word f(word a)
{
    mark = handler | 1;
    return a;
}
