/* corpus: entry=revbit */
/* Reverses the bit order of an 18-bit word. Each pass looks at the top bit
 * of IO, adds the matching low weight when it is set, then rotates IO left
 * and the weight up. zeros counts the clear bits. */

extern word count, out, weight, zeros;

JDA word revbit(word x)
{
    count = -022;                   /* isp reaches 0 after 18 passes */
    out = 0;
    zeros = 0;
    weight = 1;
    register word bits = x;
    for (;;) {
        if (++count >= 0)
            return out;
        if (bits < 0) {
            word o = out | weight;
            out = o;
        }
        if (bits >= 0)
            ++zeros;
        word w = weight;
        w = ral(w, 1);
        weight = w;
        bits = ril(bits, 1);
    }
}

word count = 0;
word out = 0;
word weight = 0;
word zeros = 0;
