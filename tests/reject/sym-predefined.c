/* reject: SYM('lac') is predefined by macro1 */
/* A label named like an instruction would redefine it for the whole program. */

JDA SYM("lac") word load(word a);

JDA SYM("lac") word load(word a)
{
    return a;
}
