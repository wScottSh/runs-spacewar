/* corpus: entry=exchange */
/* Two cursors into a table of six words: one from the front, held in a
 * pool word, and one from the back, held in the instruction that loads
 * it. exchange(k) moves the front cursor one word in when k is negative,
 * swaps the two words, adds k to the front word, quarters the old back
 * word on its way, and counts up the back word. It returns the front word
 * plus the new back word in AC, and the new back word in IO. */

word table[6] = { 1, 020, 0300, 04000, 0177777, 0400000 };
POOL word *front;
HOMED word *back;
POOL word kept;

JDA dword exchange(word k)
{
    front = table;
    back = table + 5;
    if (k < 0)
        ++front;
    register word b = *home(back);
    word f = *front;
    *back = f;
    b = b >> 2;
    *front = b;
    f = *front + k;
    *front = f;
    kept = f;
    ++*back;
    word sum = kept + *back;
    register word now = *back;
    return (dword){ sum, now };
}
