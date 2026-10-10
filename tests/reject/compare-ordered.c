/* reject: a comparison with a value other than 0 is == or != */
/* The skip group orders AC only against 0; sas and sad test sameness. */

word limit = 5;

JDA word f(word x)
{
    if (x < limit)
        return limit;
    return x;
}
