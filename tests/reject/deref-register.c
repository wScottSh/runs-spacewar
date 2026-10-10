/* reject: *p reads through a pointer p held in memory or a homed address field */
/* The machine reaches a word through a pointer by the indirect bit of an
 * instruction that names the pointer's cell; IO has no address to name. */

JSP word f(register word *p)
{
    return *p;
}
