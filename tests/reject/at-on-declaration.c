/* reject: AT places a definition, not a declaration */
/* An origin on a declaration would place nothing, so it would be decoration. */

AT(0200) JDA word f(word a);

JDA word f(word a)
{
    return -a;
}
