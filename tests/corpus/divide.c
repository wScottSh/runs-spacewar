/* corpus: entry=div10 */
/* Quotient by ten through repeated subtraction; the remainder is left in rem. */

extern word quot, rem;

JDA word div10(word x)
{
    quot = 0;
    rem = x;
    for (;;) {
        word r = rem - 012;
        if (r < 0)
            return quot;
        rem = r;
        ++quot;
    }
}

word quot = 0;
word rem = 0;
