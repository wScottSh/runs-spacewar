/* BBN divide (source lines 346-396).
 * divide: the 36-bit dividend arrives in AC (high) and IO (low), the divisor
 * by name in the word after the call (`jda dvd / lac d`). The quotient comes
 * back in AC and the remainder, with the dividend's sign, in IO.
 * integer_divide: the dividend is the single word in AC.
 * Both skip the word after the divisor unless the quotient would not fit
 * (|high dividend| >= |divisor|). Then they return to that word, with
 * |divisor| (signed like a quotient) in AC and the high dividend in IO. */

JDA SKIPS SYM("idv") dword integer_divide(word dividend, register word lo, BYNAME word divisor);
JDA SKIPS dword divide(word hi, register word lo, BYNAME word divisor);
BLOCK SKIPS dword divide_steps(register word lo, BYNAME word divisor);

ENTRY_CELL(divide) word dividend_hi;        /* dvd's entry word; later the remainder */
ENTRY_CELL(integer_divide) word quotient;   /* idv's entry word: |divisor|, then the quotient */

JDA SKIPS SYM("idv") dword integer_divide(word dividend, register word lo, BYNAME word divisor)
{
    word h = dividend;
    scr(h, lo, 17);                 /* the dividend becomes the 36-bit AC:IO pair;
                                       IO's old sign lands in its lowest bit */
    dividend_hi = h;
    return divide_steps(lo, divisor);
}

JDA SKIPS dword divide(word hi, register word lo, BYNAME word divisor)   /* dvd */
{
    dividend_hi = hi;               /* the same cell: no code */
    return divide_steps(lo, divisor);
}

BLOCK SKIPS dword divide_steps(register word lo, BYNAME word divisor)
{
    word h = divisor;
    if (h < 0)
        h = -h;
    quotient = h;
    h = dividend_hi;
    if (h < 0) {                    /* negate the 36-bit dividend */
        h = -h;
        rcr(h, lo, 18);
        h = -h;
        rcr(h, lo, 18);
    }
    h = h - quotient;
    if (h >= 0)
        goto overflow;
    for (int i = 0; i < 022; i++)   /* 18 divide steps */
        dis(h, lo, quotient);
    h = h + quotient;               /* restore the last step's remainder */
    quotient = lo;
    lo = 0;
    rcr(h, lo, 1);
    lo = dividend_hi;
    if (lo < 0)
        h = -h;                     /* the remainder takes the dividend's sign */
    dividend_hi = h;
    lo = divisor ^ dividend_hi;     /* negative when the quotient is */
    skip_return();
overflow:
    h = quotient;
    if (lo < 0)
        h = -h;
    return (dword){ h, dividend_hi };
}
