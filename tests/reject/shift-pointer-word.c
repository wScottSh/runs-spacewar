/* reject: step points to a shift */
/* A pointer that xct runs through must point into shifts. */

HOMED const shift *step;
word steps[2] = { 1, 2 };

JDA word f(word a)
{
    step = steps;
    return xct(*home(step), a);
}
