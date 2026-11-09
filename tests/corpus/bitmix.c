/* corpus: entry=mix */
/* Mixes the halves of a word with masks, shifts and a 36-bit rotate. */

extern word seed, low, high;

JDA word mix(word x)
{
    register word io = seed;
    word a = x;
    rcl(a, io, 18);                 /* exchange AC and IO through the pair */
    high = a;
    a = ((x & 0707070) | seed) ^ low;
    a = a << 11;
    if (a == 0) {
        return high;
    } else {
        low = a;
    }
    a = -07;
    a = a + high;
    return a;
}

word seed = 0505050;
word low = 017;
word high = 0;
