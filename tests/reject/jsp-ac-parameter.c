/* reject: a JSP function receives its return address in AC */
/* jsp overwrites AC with the return address, so an AC parameter cannot arrive. */

JSP word twice(word v)
{
    v = v + v;
    return v;
}
