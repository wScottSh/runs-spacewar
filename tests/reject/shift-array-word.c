/* reject: steps holds a shift */
/* A shift table is read through a pointer into it and executed. */

HOMED const shift *step;
shift steps[2] = { I_SAR(1), 0 };

JDA word f(word a)
{
    step = steps;
    return xct(*home(step), a);
}
