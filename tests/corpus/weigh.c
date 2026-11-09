/* corpus: entry=blend */
/* weigh multiplies the low 9 bits of w by the low 9 bits of a word passed
 * by name, in nine multiply steps; the product comes back in AC:IO. blend
 * weighs x against two stored items and adds the low half of the first
 * product to the high half of the second. */

JDA dword weigh(word w, BYNAME word item);
JDA word blend(word x);
BLOCK word add_low(word s);

ENTRY_CELL(weigh) word weight;      /* weigh's entry word: w, then its low 9 bits */
extern word first, second, low;

JDA dword weigh(word w, BYNAME word item)
{
    word m = w & 0777;
    weight = m;
    m = item;
    m = m & 0777;
    register word lo = m;
    word h = 0;
    for (int i = 0; i < 9; i++)
        mus(h, lo, weight);
    return (dword){ h, lo };
}

BLOCK word add_low(word s)
{
    s = s + low;
    return s;
}

JDA word blend(word x)
{
    dword p = weigh(x, first);
    low = p.lo;
    p = weigh(x, second);
    word s = p.hi;
    return add_low(s);
}

word first = 0543;
word second = 0123456;
word low = 0;
