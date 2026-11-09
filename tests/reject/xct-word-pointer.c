/* reject: *home(p) for a pointer p to a shift */
/* xct through a pointer runs what it points to, which must be a shift. */

HOMED const word *step;
word steps[2] = { 1, 2 };

JDA word f(word a)
{
    step = steps;
    return xct(*home(step), a);
}
