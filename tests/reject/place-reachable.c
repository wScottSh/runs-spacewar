/* reject: control reaches PLACE */
/* Words laid out where control can reach them would run as instructions. */

word template = 0;

JDA word f(word a)
{
    if (a < 0)
        return a;
    PLACE(template);
    return template;
}
