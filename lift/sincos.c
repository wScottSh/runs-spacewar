/* Sine-cosine subroutine, Adams Associates (source lines 190-254).
 * The angle arrives in AC, within +-2 pi, binary point right of bit 3; the
 * answer has its binary point right of bit 0. cosine shifts the angle by
 * pi/2 and joins sine's series; both return through the series' exit.
 * The series keeps its working values in the two entry words. */

#define HALF_PI     062210
#define TWO_PI      0311040
#define ONE         0377777         /* largest fraction: the answer saturates here */

/* The reduced angle times 2/pi is x; the answer is the odd polynomial
 * x (C1 + x^2 (C3 + x^2 (C5 + x^2 C7))) scaled up by 8, each product the
 * high half of a multiply. */
#define TWO_OVER_PI 0242763
#define C1          0144417
#define C3          -0245266
#define C5          0121312
#define C7          -021674

JDA dword multiply(word a, BYNAME word b);

JDA word cosine(word angle);
JDA word sine(word angle);
BLOCK word sine_series(word a);

ENTRY_CELL(sine) word x;            /* sin's entry word: the scaled angle */
ENTRY_CELL(cosine) word x_squared;  /* cos's entry word: x^2 ... */
ENTRY_CELL(cosine) word result;     /* ... then the answer */

JDA word cosine(word angle)  /* cos */
{
    x = HALF_PI + angle;            /* cos a = sin(a + pi/2) */
    return sine_series(x);
}

JDA word sine(word angle)  /* sin */
{
    return sine_series(angle);
}

BLOCK word sine_series(word a)
{
    if (a < 0)
reduce: a += TWO_PI;
    a -= HALF_PI;
    if (a >= 0)
        goto past_quarter;
    a += HALF_PI;
series:                             /* a is in [0, pi/2] */
    a = ral(a, 2);
    x = multiply(a, TWO_OVER_PI).hi;
    x_squared = multiply(x, x).hi;
    a = multiply(x_squared, C7).hi + C5;
    a = multiply(a, x_squared).hi + C3;
    a = multiply(a, x_squared).hi + C1;
    {
        dword p = multiply(a, x);
        scl(p.hi, p.lo, 3);
        result = p.hi;
    }
    if ((result ^ x) < 0) {         /* the series overshot +-1 */
        a = ONE;
        register word sign = x;
        if (sign < 0)
            a = -a;
        return a;
    }
    return result;

past_quarter:                       /* fold a beyond pi/2 back into [0, pi/2] */
    a = -a + HALF_PI;
    if (a >= 0)
        goto series;
    a += HALF_PI;
    if (a >= 0) {
        a -= HALF_PI;
        goto series;
    }
    a -= HALF_PI;
    goto reduce;
}
