/* reject: the START function is a BLOCK with no parameters */
/* The machine enters the start address by a jump from the loader: there is
 * no return address and no argument to receive. */

START JDA word begin(word a)
{
    return a;
}
