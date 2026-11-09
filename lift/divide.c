/* BBN divide (source lines 346-396).
 * divide: the 36-bit dividend arrives in AC (high) and IO (low), the divisor
 * by name in the word after the call (`jda dvd / lac d`). The quotient comes
 * back in AC and the remainder, with the dividend's sign, in IO.
 * integer_divide: the dividend is the single word in AC.
 * Both skip the word after the divisor unless the quotient would not fit
 * (|high dividend| >= |divisor|). Then they return to that word, with
 * |divisor| (signed like a quotient) in AC and the high dividend in IO. */

JDA SKIPS dword integer_divide(word dividend, register word low, BYNAME word divisor);
JDA SKIPS dword divide(word high, register word low, BYNAME word divisor);
BLOCK SKIPS dword divide_steps(register word low, BYNAME word divisor);

ENTRY_CELL(divide) word dividend_high;      /* dvd's entry word; later the remainder */
ENTRY_CELL(integer_divide) word quotient;   /* idv's entry word: |divisor|, then the quotient */

JDA SKIPS dword integer_divide(word dividend, register word low, BYNAME word divisor)  /* idv */
{
    word high = dividend;
    scr(high, low, 17);             /* the dividend becomes the 36-bit AC:IO pair;
                                   IO's old sign lands in its lowest bit */
    dividend_high = high;
    return divide_steps(low, divisor);
}

JDA SKIPS dword divide(word high, register word low, BYNAME word divisor)  /* dvd */
{
    dividend_high = high;           /* the same cell: no code */
    return divide_steps(low, divisor);
}

BLOCK SKIPS dword divide_steps(register word low, BYNAME word divisor)
{
    word magnitude = divisor;
    if (magnitude < 0)
        magnitude = -magnitude;
    quotient = magnitude;
    word high = dividend_high;
    if (high < 0) {                 /* negate the 36-bit dividend */
        high = -high;
        rcr(high, low, 18);
        high = -high;
        rcr(high, low, 18);
    }
    high = high - quotient;
    if (high >= 0)
        goto overflow;
    for (int i = 0; i < 022; i++)   /* 18 divide steps */
        dis(high, low, quotient);
    high = high + quotient;         /* restore the last step's remainder */
    quotient = low;
    low = 0;
    rcr(high, low, 1);
    low = dividend_high;
    if (low < 0)
        high = -high;               /* the remainder takes the dividend's sign */
    dividend_high = high;
    low = divisor ^ dividend_high;  /* negative when the quotient is */
    skip_return();
overflow:
    high = quotient;
    if (low < 0)
        high = -high;
    return (dword){ high, dividend_high };
}
