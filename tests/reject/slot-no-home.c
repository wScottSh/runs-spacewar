/* reject: has no home */
/* A HOMED insn is laid out where it runs. One that never runs has no
 * place in the code, and its stores would name nothing. */

HOMED insn shift = I_HLT;

JDA word f(word a)
{
    shift = a;
    return a;
}
