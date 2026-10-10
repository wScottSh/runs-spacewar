/* reject: a program starts at one START function */

word ticks = 0;

START BLOCK void first(void)
{
again:
    ++ticks;
    goto again;
}

START BLOCK void second(void)
{
again:
    ++ticks;
    goto again;
}
