/* reject: SYM('stax') is predefined by macro1 */
/* macro1 reads a symbol it has not seen defined as the pseudo-op sharing
 * its first three letters, so `stax` would be `start`. */

JDA SYM("stax") word load(word a);

JDA SYM("stax") word load(word a)
{
    return a;
}
